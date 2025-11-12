#include <hwtHls/llvm/intrinsic/metadataWithBitrange.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/utils/bitWidthInfo.h>

using namespace llvm;

namespace hwtHls::MetadataBitRanges {

// :param mdNode: input mdNode which is MDTuple of MDTuples with 2 integers (left, right boundary)
// :note: ranges are in left enclosed format, <0, 2) contains values 0, 1
void fromMetadata(MDNode *mdTuple, BitRanges &res) {
	assert(mdTuple);
	auto getMdIntFromMd = [](Metadata *md) {
		assert(md);
		auto mdV = cast<ValueAsMetadata>(md);
		assert(mdV);
		auto v = mdV->getValue();
		assert(isa<ConstantInt>(v));
		return dyn_cast<ConstantInt>(v)->getZExtValue();
	};
	for (auto &o : mdTuple->operands()) {
		auto rTuple = dyn_cast<MDTuple>(o.get());
		assert(rTuple);
		assert(rTuple->getNumOperands() == 2);
		auto l = getMdIntFromMd(rTuple->getOperand(0).get());
		auto h = getMdIntFromMd(rTuple->getOperand(1).get());
		res.push_back( { l, h });
	}
}

// :attention: arr is assumed to be sorted (lowest first), and intervalus must be non overlapping <low, high)
MDTuple* rangeMetadataToMetadata(LLVMContext &Ctx, const BitRanges &arr) {
	auto *u64 = IntegerType::get(Ctx, 64);
	auto getU64md = [u64](uint64_t v) {
		return ValueAsMetadata::get(ConstantInt::get(u64, v));
	};
	SmallVector<Metadata*> mds;
	for (auto r : arr) {
		auto rMd = MDTuple::get(Ctx, { getU64md(r.first), getU64md(r.second) });
		mds.push_back(rMd);
	}
	return MDTuple::get(Ctx, mds);
}

// based on https://www.geeksforgeeks.org/dsa/merging-intervals/
// :note: modified so that 1b range overlap is required for intervals to merge
void mergeOverlapedIntervals(BitRanges &arr, BitRanges &res) {
	llvm::sort(arr);
	res.push_back(arr[0]);
	for (unsigned i = 1; i < arr.size(); i++) {
		auto &last = res.back();
		auto &curr = arr[i];
		assert(curr.first < curr.second);
		// If current interval overlaps with the last merged
		// interval, merge them
		// :note: e.g. if last ending on bit 4 (second==5) and the cur begins on bit 4 (first==4)
		if (last.second > curr.first) {
			last.second = std::max(last.second, curr.second);
		} else {
			res.push_back(curr);
		}
	}
}

void intervalsApplySlice(const BitRanges &arr, size_t offset, size_t width,
		BitRanges &res) {
	for (auto r : arr) {
		if (r.second <= offset) {
			continue; // before selected range
		} else if (r.first >= width) {
			continue; // after selected range
		}
		if (r.first < offset) {
			r.first = 0;
		} else {
			r.first -= offset;
		}
		assert(r.second > offset);
		r.second -= offset;
		if (r.second >= width) {
			r.second = width;
			assert(r.first < r.second);
			res.push_back(r);
			break;
		}
		assert(r.first < r.second);
		res.push_back(r);
	}
}
void intervalsApplyOffset(const BitRanges &arr, size_t offset, BitRanges &res) {
	for (auto r : arr) {
		res.push_back( { r.first + offset, r.second + offset });
	}
}

bool updateRangeMetadata(Instruction &I, unsigned MDKindID,
		const BitRanges &ranges) {
	auto &Ctx = I.getContext();
	auto curMd = I.getMetadata(MDKindID);
	if (!curMd) {
		MDNode *newMd;
		if (ranges.empty()) {
			newMd = MDTuple::get(Ctx, { });
		} else {
			newMd = rangeMetadataToMetadata(Ctx, ranges);
		}
		I.setMetadata(MDKindID, newMd);
		return true;
	}

	auto mdTupleCur = dyn_cast<MDTuple>(curMd);
	if (mdTupleCur->getNumOperands() == 0)
		return false; // "I" has already range over all bits

	if (ranges.empty()) {
		I.setMetadata(MDKindID, MDTuple::get(Ctx, { }));
		return true;
	}

	BitRanges rangesUnique;
	BitRanges _rangesOriginal;
	fromMetadata(curMd, _rangesOriginal);
	{
		BitRanges _ranges(ranges);
		_ranges.insert(_ranges.end(), _rangesOriginal.begin(), _rangesOriginal.end());
		mergeOverlapedIntervals(_ranges, rangesUnique);
		// :note: _ranges are now invalid

	}
	if (_rangesOriginal == rangesUnique) // if new merged uniqueified data is the same as current
		return false;
	assert(rangesUnique.size());
	MDNode *newMd;
	if (rangesUnique.size() == 1 && rangesUnique.front().first == 0
			&& rangesUnique.front().second
					== I.getType()->getIntegerBitWidth()) {
		newMd = MDTuple::get(I.getContext(), { }); // now all bits are part of the mask
	} else {
		newMd = rangeMetadataToMetadata(I.getContext(), rangesUnique);
	}
	if (curMd == newMd)
		return false;
	I.setMetadata(MDKindID, newMd);
	return true;
}

void propagateUseToDefBitwidthReducing(OffsetWidthValue src, Instruction &srcI,
		unsigned MDKindID, const BitRanges &bitRanges) {
	// :note: updating from slice src operand from slice instruction
	// translate ranges to original bit vector bit indexing
	BitRanges OpIbitRanges;
	if (bitRanges.empty()) {
		assert(src.width > 0);
		if (!src.isIdentity())
			OpIbitRanges.push_back( { src.offset, src.offset + src.width });
	} else {
		intervalsApplyOffset(bitRanges, src.offset, OpIbitRanges);
		if (OpIbitRanges.empty())
			return; // no interval selected
	}
	if (updateRangeMetadata(srcI, MDKindID, OpIbitRanges)) {
		propagateBiDir(srcI, MDKindID, OpIbitRanges);
	}
}

void propagateDefToUseBitwidthReducing(OffsetWidthValue uSlice,
		Instruction &userI, unsigned MDKindID, const BitRanges &bitRanges) {
	// :note: updating slice instruction from its src operand
	BitRanges OpIbitRanges;
	if (bitRanges.empty()) {
		// whole interval selected
	} else {
		intervalsApplySlice(bitRanges, uSlice.offset, uSlice.width,
				OpIbitRanges);
		if (OpIbitRanges.empty())
			return; // no interval selected
		else if (OpIbitRanges.size() == 1 && OpIbitRanges.front().first == 0
				&& OpIbitRanges.front().second == uSlice.width)
			OpIbitRanges.clear(); // whole interval selected
	}
	if (updateRangeMetadata(userI, MDKindID, OpIbitRanges)) {
		propagateBiDir(userI, MDKindID, OpIbitRanges);
	}
}

// :note: MDKindID = M.getContext().getMDKindID(mdName)
void propagateBiDir(Instruction &I, unsigned MDKindID,
		const BitRanges &bitRanges) {
	//errs() << "propagateBiDir: " << I << "\n";
	//for (auto r: bitRanges) {
	//	errs () << "   "  << r.first << ":" << r.second << "\n";
	//}
	// if this is some form of bit manipulation propagate use->def
	// to set metadata on original bit vector(s)
	if (auto CI = dyn_cast<CallInst>(&I)) {
		//if (IsBitConcat(CI)) {
		//	for (Use &_Op : CI->args()) {
		//		auto Op = _Op.get();
		//		auto OpI = dyn_cast<Instruction>(Op);
		//		if (!OpI)
		//			continue;
		//		if (OpI->getMetadata(MDKindID))
		//			continue;
		//		if (getIntegerBitWidthOr1(Op) != width)
		//			continue;
		//		OpI->setMetadata(MDKindID, mdNode);
		//		propagateBiDir(*OpI,
		//				MDKindID, mdNode);
		//	}
		//
		//} else

		if (IsBitRangeGet(CI)) {
			auto OpI = dyn_cast<Instruction>(CI->getArgOperand(0));
			if (OpI) {
				auto owv = OffsetWidthValue::fromValue(CI);
				propagateUseToDefBitwidthReducing(owv, *OpI, MDKindID,
						bitRanges);
			}
		}
	} else if (auto cast = dyn_cast<CastInst>(&I)) { // ZExtInst, SExtInst, ...
		if (auto src = dyn_cast<Instruction>(cast->getOperand(0))) {
			auto owv = OffsetWidthValue::fromValue(cast);
			propagateUseToDefBitwidthReducing(owv, *src, MDKindID, bitRanges);
		}
	}
	// propagate def->use
	for (User *U : I.users()) {
		auto UI = dyn_cast<Instruction>(U);
		if (!UI) {
			continue;
		}

		if (auto Phi = dyn_cast<PHINode>(U)) {
			if (updateRangeMetadata(*Phi, MDKindID, bitRanges)) {
				propagateBiDir(*Phi, MDKindID, bitRanges);
			}
		} else if (auto cast = dyn_cast<CastInst>(U)) { // ZExtInst, SExtInst, ...
			auto owv = OffsetWidthValue::fromValue(cast);
			propagateDefToUseBitwidthReducing(owv, *cast, MDKindID, bitRanges);
		} else if (auto call = dyn_cast<CallInst>(U)) {
			// IsBitConcat(call) ||
			if (IsBitRangeGet(call)) {
				auto owv = OffsetWidthValue::fromValue(call);
				propagateDefToUseBitwidthReducing(owv, *call, MDKindID,
						bitRanges);
			}
		}
	}
}

void setAndPropagateBiDir(llvm::Instruction &I, unsigned MDKindID,
		const BitRanges &bitRanges) {
	auto md = rangeMetadataToMetadata(I.getContext(), bitRanges);
	I.setMetadata(MDKindID, md);
	propagateBiDir(I, MDKindID, bitRanges);
}

bool isSelected(llvm::Instruction &I, unsigned MDKindID) {
	return isSelected(I, MDKindID, {0, I.getType()->getIntegerBitWidth()});
}

bool isSelected(llvm::Instruction &I, unsigned MDKindID, std::pair<size_t, size_t> range) {
	auto md = I.getMetadata(MDKindID);
	if (md) {
		auto mdTuple = dyn_cast<MDTuple>(md);
		assert(mdTuple);
		if (mdTuple->getNumOperands() == 0)
			return true;
		auto getMdIntFromMd = [](Metadata *md) {
			auto v = cast<ValueAsMetadata>(md)->getValue();
			assert(isa<ConstantInt>(v));
			return dyn_cast<ConstantInt>(v)->getZExtValue();
		};
		for (auto& o: mdTuple->operands()) {
			auto rTuple = dyn_cast<MDTuple>(o.get());
			assert(rTuple);
			assert(rTuple->getNumOperands() == 2);
			auto l = getMdIntFromMd(rTuple->getOperand(0).get());
			auto h = getMdIntFromMd(rTuple->getOperand(1).get());
			if (l <= range.first && h >= range.second)
				return true;
			else if (h < range.first)
				return false;
		}
		return false;
	}
	auto owv = OffsetWidthValue::fromValue(&I);
	if (owv.isIdentity())
		return false;
	auto srcI = dyn_cast<Instruction>(owv.value);
	if (!srcI)
		return false;
	return isSelected(*srcI, MDKindID, {range.first + owv.offset, range.second + owv.offset});
}

}
