#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/ADT/SmallString.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/bitMath.h>

using namespace llvm;
namespace hwtHls {

KnownBitRangeInfo::KnownBitRangeInfo(unsigned bitwidth) :
		dstBeginBitI(0), srcBeginBitI(0), width(bitwidth), src(nullptr) {
}
KnownBitRangeInfo::KnownBitRangeInfo(const ConstantInt *CI) :
		dstBeginBitI(0), srcBeginBitI(0), width(CI->getBitWidth()), src(CI) {
}
KnownBitRangeInfo::KnownBitRangeInfo(const Value *V) :
		dstBeginBitI(0), srcBeginBitI(0), width(
				V->getType()->isIntegerTy() ?
						V->getType()->getIntegerBitWidth() : 1), src(V) {
}

KnownBitRangeInfo::KnownBitRangeInfo(const OffsetWidthValue &owv,
		unsigned dstBeginBitI) :
		dstBeginBitI(dstBeginBitI), srcBeginBitI(owv.offset), width(owv.width), src(
				owv.value) {

}

unsigned KnownBitRangeInfo::dstEndBitI() const {
	return dstBeginBitI + width;
}

bool KnownBitRangeInfo::overlapsThisOnLeftInDst(
		const KnownBitRangeInfo &itemOnRight) const {
	assert(dstBeginBitI <= itemOnRight.dstBeginBitI);
	return dstEndBitI() > itemOnRight.dstBeginBitI; // this ending after other begin
}

KnownBitRangeInfo KnownBitRangeInfo::slice(unsigned offset,
		unsigned width) const {
	assert(offset < 0xffffff && width < 0xffffff && "Sanity check");
	assert(width > 0);
	assert(
			srcBeginBitI + offset + width
					<= src->getType()->getIntegerBitWidth()
					&& "Bit range does not overflow");
	KnownBitRangeInfo res(width);
	if (auto *CI = dyn_cast<const ConstantInt>(src)) {
		auto v = CI->getValue();
		v.lshrInPlace(offset);
		assert(res.srcBeginBitI == 0);
		res.src = ConstantInt::get(CI->getContext(), v.trunc(width));
		res.srcBeginBitI = 0;
	} else {
		res.src = src;
		res.srcBeginBitI = srcBeginBitI + offset;
	}
	res.dstBeginBitI = dstBeginBitI + offset;
	return res;
}

bool KnownBitRangeInfo::isValue(const llvm::Value *V) const {
	return *this == KnownBitRangeInfo(V);
}

void KnownBitRangeInfo::print(raw_ostream &O, bool IsForDebug) const {
	O << "[" << (dstBeginBitI + width) << ":" << dstBeginBitI << "]=(";
	if (dyn_cast<ConstantInt>(src)) {
		O << *src;
	} else {
		if (src->hasName())
			O << "%" << src->getName();
		else {
			O << "%" << src;
		}
	}
	O << ")[" << (srcBeginBitI + width) << ":" << srcBeginBitI << "]";
}
bool KnownBitRangeInfo::operator!=(const KnownBitRangeInfo &rhs) const {
	return (dstBeginBitI != rhs.dstBeginBitI || srcBeginBitI != rhs.srcBeginBitI
			|| width != rhs.width || src != rhs.src);
}
bool KnownBitRangeInfo::operator==(const KnownBitRangeInfo &rhs) const {
	return (dstBeginBitI == rhs.dstBeginBitI && srcBeginBitI == rhs.srcBeginBitI
			&& width == rhs.width && src == rhs.src);
}

void RangeSequenceIterator::appendNoCheck(
		std::vector<KnownBitRangeInfo>::const_iterator &v, unsigned vEnd,
		std::vector<UniqRangeSequence> &res, bool isV1) {
	unsigned begin = v->dstBeginBitI;
	unsigned previouslyConsummedBits = 0;
	if (vEnd > begin) {
		previouslyConsummedBits = vEnd - begin;
		begin = vEnd;
	}
	unsigned end = v->width - previouslyConsummedBits;
	const KnownBitRangeInfo *v0 = nullptr;
	const KnownBitRangeInfo *v1 = nullptr;
	if (isV1) {
		v1 = &*v;
	} else {
		v0 = &*v;
	}

	res.push_back(UniqRangeSequence( { begin, end - begin, v0, v1 }));
	vEnd = end;
	++v;
}

std::vector<UniqRangeSequence> RangeSequenceIterator::uniqueRanges(
		const std::vector<KnownBitRangeInfo> &vec0,
		const std::vector<KnownBitRangeInfo> &vec1) {
	std::vector<UniqRangeSequence> res;

	auto v0 = vec0.begin();
	auto v1 = vec1.begin();
	// last offset for input
	unsigned lastEnd = 0;
	//assert(
	//		vec0.back().dstEndBitI() == vec1.back().dstEndBitI()
	//				&& "data must be of same total width");
	// iterate both vectors and discover next point where some of interval ends and use it to consume
	// this number of bits from both vectors and produce record to output res vector
	for (; v0 != vec0.end() || v1 != vec1.end();) {
		if (v0 == vec0.end()) {
			assert(
					v1->dstBeginBitI == lastEnd
							&& "vec1 must be continuous sequence");
			appendNoCheck(v1, lastEnd, res, true);
			continue;
		} else if (v1 == vec1.end()) {
			assert(
					v0->dstBeginBitI == lastEnd
							&& "vec0 must be continuous sequence");
			appendNoCheck(v0, lastEnd, res, false);
			continue;
		}
		// 1 interval of "a" may span over multiple interval from "b" and same for "b" to "a"
		// following alg. always goes 1 boundary in any interval at the time
		unsigned v0Begin = std::max(lastEnd, v0->dstBeginBitI);
		unsigned v1Begin = std::max(lastEnd, v1->dstBeginBitI);
		unsigned curBegin = std::min(v0Begin, v1Begin);
		unsigned curEnd; // the second lowest number in  v0Begin, v1Begin, v0->dstEndBitI(), v1->dstEndBitI()
		if (v0Begin == v1Begin) {
			curEnd = std::min(v0->dstEndBitI(), v1->dstEndBitI());
		} else if (v0Begin < v1Begin) {
			curEnd = std::min(std::min(v1Begin, v0->dstEndBitI()),
					v1->dstEndBitI());
		} else {
			curEnd = std::min(std::min(v0Begin, v0->dstEndBitI()),
					v1->dstEndBitI());
		}
		assert(curEnd > curBegin);
		const KnownBitRangeInfo *_v0 = nullptr;
		const KnownBitRangeInfo *_v1 = nullptr;
		if (isInInterval(curBegin, curEnd, v0Begin)) {
			_v0 = &*v0;
			assert(
					v0->dstBeginBitI <= lastEnd
							&& "vec0 must be continuous sequence");
			if (curEnd == v0->dstEndBitI())
				++v0;
		}
		if (isInInterval(curBegin, curEnd, v1Begin)) {
			_v1 = &*v1;
			assert(
					v1->dstBeginBitI <= lastEnd
							&& "vec1 must be continuous sequence");
			if (curEnd == v1->dstEndBitI())
				++v1;
		}
		assert(_v0 && "vec0 must be continuous interval sequence");
		assert(_v1 && "vec1 must be continuous interval sequence");
		res.push_back(
				UniqRangeSequence( { curBegin, curEnd - curBegin, _v0, _v1 }));
		lastEnd = curEnd;
		// v0 <-->
		// v1 <-->

		// v0 <-->
		// v1     <-->

		// v0 <-->
		// v1 <-->

		// v0 <--->
		// v1  <-->

		// v0 <----->
		// v1  <-->
	}
	assert(res.size());
	return res;
}

VarBitConstraint::VarBitConstraint(unsigned bitWidth) :
		useMask(bitWidth, 0) {
}

VarBitConstraint::VarBitConstraint(const ConstantInt *CI) :
		useMask(CI->getBitWidth(), 0) {
	replacements.push_back(KnownBitRangeInfo(CI));
}

VarBitConstraint::VarBitConstraint(const Value *V) :
		useMask(
				V->getType()->isIntegerTy() ?
						V->getType()->getIntegerBitWidth() : 1, 0) {
	replacements.push_back(KnownBitRangeInfo(V)); // represent value with this value
}

VarBitConstraint::VarBitConstraint(const VarBitConstraint &obj) :
		useMask(obj.useMask), replacements(obj.replacements), operandUseMask(
				obj.operandUseMask) {
}

VarBitConstraint VarBitConstraint::fromConcat(const llvm::CallInst *V) {
	VarBitConstraint res(V);
	std::vector<KnownBitRangeInfo> newParts; // high first
	for (const auto &O : V->args()) {
		VarBitConstraint op(O);
		if (auto OC = dyn_cast<CallInst>(O)) {
			if (IsBitConcat(OC)) {
				op = fromConcat(OC);
			} else if (IsBitRangeGet(OC)) {
				auto OWV = OffsetWidthValue::fromValue(OC);
				size_t dstOffset = 0;
				if (!newParts.empty()) {
					dstOffset = newParts.back().dstBeginBitI + newParts.back().width;
				}
				newParts.push_back(KnownBitRangeInfo(OWV, dstOffset));
				assert(op.consistencyCheck());
				continue;
			}
		}
		assert(op.consistencyCheck());
		for (auto &opop : op.replacements) {
			newParts.push_back(opop);
		}
	}
	res.replacements.clear();
	// to lowest first
	unsigned dstOff = 0;
	for (auto &i : newParts) {
		i.dstBeginBitI = dstOff;
		res.replacements.push_back(i);
		dstOff += i.width;
	}
	return res;
}

bool VarBitConstraint::valuesHaveSameMeaning(const llvm::Value *V0, const llvm::Value *V1) {
	if (V0 == V1)
		return true;
	if (V0->getType() != V1->getType())
		return false;
	if (auto V0C = dyn_cast<CallInst>(V0)) {
		if (auto V1C = dyn_cast<CallInst>(V1)) {
			if (IsBitConcat(V0C) && IsBitConcat(V1C)) {
				return fromConcat(V0C).replacements == fromConcat(V1C).replacements;
			}
		}
	}
	return false;
}

bool VarBitConstraint::_valuesHaveSameMeaning(const llvm::Value *V1) const {
	assert(useMask.isAllOnes());
	if (auto V1C = dyn_cast<CallInst>(V1)) {
		if (IsBitConcat(V1C)) {
			return replacements == fromConcat(V1C).replacements;
		}
	}
	if (replacements.size() == 1) {
		if (replacements[0].isValue(V1))
			return true;
		if (auto V1CI = dyn_cast<CallInst>(V1)) {
			if (IsBitRangeGet(V1CI)) {
				auto OWV = OffsetWidthValue::fromValue(const_cast<Value*>(V1));
				size_t dstOffset = 0;
				return replacements[0] == KnownBitRangeInfo(OWV, dstOffset);
			}
		}
	}
	return false;
}

bool VarBitConstraint::valuesHaveSameMeaning(const llvm::Value *V1) const {
	bool hasSameWidth;
	if (V1->getType()->isIntegerTy())
		hasSameWidth = useMask.getBitWidth() == V1->getType()->getIntegerBitWidth();
	else
		hasSameWidth = useMask.getBitWidth() == 1 && useMask.getZExtValue();
	if (useMask.isAllOnes()) {
		if (hasSameWidth)
			return _valuesHaveSameMeaning(V1);
		else
			return false;
	} else {
		if (hasSameWidth || !V1->getType()->isIntegerTy())
			return false; // after pruning this would have less bits than V1
		else if (useMask.popcount() != V1->getType()->getIntegerBitWidth()) {
			return false; // after pruning this would have a different number of bits than V1
		} else {
			return toAllOnesUseMask()._valuesHaveSameMeaning(V1);
		}
	}
}

void VarBitConstraint::addAllSetOperandMask(unsigned width) {
	operandUseMask.push_back(APInt::getAllOnes(width));
}
void VarBitConstraint::clearAllOperandMasks() {
	for (auto &om : operandUseMask) {
		om.clearAllBits();
	}
}
void VarBitConstraint::clearAllOperandMasks(unsigned lowBitI,
		unsigned highBitI) {
	APInt m = ~APInt::getBitsSet(operandUseMask[0].getBitWidth(), lowBitI,
			highBitI);
	for (auto &om : operandUseMask) {
		om &= m;
	}
}

llvm::APInt VarBitConstraint::getTrullyComputedBitMask(
		const llvm::Value *selfValue) const {
	bool selfIsCastOrSliceOrConcat = isa<CastInst>(selfValue);
	if (!selfIsCastOrSliceOrConcat) {
		if (auto C = dyn_cast<CallInst>(selfValue)) {
			if (IsBitRangeGet(C) || IsBitConcat(C)) {
				selfIsCastOrSliceOrConcat = true;
			}
		}
	}
	APInt m(useMask.getBitWidth(), 0);
	for (const KnownBitRangeInfo &r : replacements) {
		if (!isa<ConstantData>(r.src)
				&& (selfIsCastOrSliceOrConcat || r.src == selfValue)) {
			m.setBits(r.dstBeginBitI, r.dstBeginBitI + r.width);
		}
	}
	return m;
}


VarBitConstraint VarBitConstraint::toAllOnesUseMask() const {
	if (useMask.isAllOnes())
		return *this;
	else if (useMask.isZero())
		return VarBitConstraint(0u);

	VarBitConstraint res(useMask.popcount());
	res.useMask.setAllBits();
	for (const auto& r: replacements) {
		auto useM = useMask.extractBits(r.width, r.dstBeginBitI);
		if (useM.isAllOnes())
			res.replacements.push_back(r);
		else {
			iterUsedBitRangeSlices(useM, [&res, &r](size_t offset, size_t width) {
				res.replacements.push_back(r.slice(offset, width));
			});
		}
	}
	assert(res.consistencyCheck());
	return res;
}

//void VarBitConstraint::_srcUnionInplaceSelf(const llvm::Value *parent,
//		uint64_t offset, uint64_t width,
//		std::vector<KnownBitRangeInfo> &newList) {
//	IRBuilder<> builder(parent->getContext());
//	KnownBitRangeInfo kbri(width);
//	kbri.srcBeginBitI = kbri.dstBeginBitI = offset;
//	srcUnionInplaceAddFillUp(newList, parent, kbri.dstBeginBitI);
//	srcUnionPushBackWithMerge(newList, kbri);
//}
void VarBitConstraint::srcUnionInplace(const VarBitConstraint &other,
		const llvm::Value *parent, bool reduceUndefs) {
	std::vector<KnownBitRangeInfo> newList;
	newList.reserve(replacements.size() + other.replacements.size());
	RangeSequenceIterator rsa;
	assert(replacements.size());
	assert(other.replacements.size());
#ifndef NDEBUG
	size_t prevEndIndex = 0;
#endif
	for (const auto &item : rsa.uniqueRanges(replacements, other.replacements)) {
		assert(item.v0 || item.v1);
		assert(item.width);
		assert(item.begin == prevEndIndex);
#ifndef NDEBUG
		prevEndIndex = item.begin + item.width;
#endif

		if (item.v0 && item.v1) {
			assert(item.begin >= item.v0->dstBeginBitI);
			assert(item.begin >= item.v1->dstBeginBitI);
			if (isa<UndefValue>(item.v0->src)
					&& (reduceUndefs || isa<UndefValue>(item.v1->src))) {
				srcUnionPushBackWithMerge(newList, *item.v1,
						item.begin - item.v1->dstBeginBitI, item.width);
				continue;
			} else if (reduceUndefs && isa<UndefValue>(item.v1->src)) {
				srcUnionPushBackWithMerge(newList, *item.v0,
						item.begin - item.v0->dstBeginBitI, item.width);
				continue;
			} else if (item.v0->src == item.v1->src
					&& item.v0->dstBeginBitI - item.v0->srcBeginBitI
							== item.v1->dstBeginBitI - item.v1->srcBeginBitI) {
				// both variants are specifying same bits for the item
				srcUnionPushBackWithMerge(newList, *item.v0,
						item.begin - item.v0->dstBeginBitI, item.width);
				continue;
			} else {
				auto _v0 = dyn_cast<ConstantInt>(item.v0->src);
				auto _v1 = dyn_cast<ConstantInt>(item.v1->src);
				if (_v0 && _v1) {
					assert(item.begin >= item.v0->dstBeginBitI);
					assert(item.begin >= item.v1->dstBeginBitI);
					// prepare values exactly selected by this item
					auto v0 = _v0->getValue().extractBits(item.width,
							item.v0->srcBeginBitI
									+ (item.begin - item.v0->dstBeginBitI));
					auto v1 = _v1->getValue().extractBits(item.width,
							item.v1->srcBeginBitI
									+ (item.begin - item.v1->dstBeginBitI));
					auto equalBits = ~(v0 ^ v1);
					// extract longest sequences of equal bits,
					// for sequences of non equal bits add slice or original value because we can not reduce it entirely
					int eqSeqStart = -1;
					//int neSeqStart = 0;
					auto end = item.width;
					for (unsigned i = 0; i <= end; ++i) {
						if (i < end && equalBits[i]) {
							// start or continue of equal bit sequence
							if (eqSeqStart == -1) {
								//if (neSeqStart != -1 && neSeqStart != (int)i) {
								//	// end of non equal bit sequence
								//	srcUnionInplaceAddFillUp(newList, parent, i);
								//	neSeqStart = -1;
								//}
								eqSeqStart = i;
							}
						} else if (eqSeqStart != -1) {
							// end of equal sequence
							IRBuilder<> builder(item.v0->src->getContext());
							auto CI = builder.getInt(
									v0.extractBits(i - eqSeqStart, eqSeqStart));
							KnownBitRangeInfo kbri(CI);
							kbri.dstBeginBitI = item.begin + eqSeqStart;
							srcUnionInplaceAddFillUp(newList, parent,
									kbri.dstBeginBitI);
							srcUnionPushBackWithMerge(newList, kbri, 0,
									kbri.width);
							eqSeqStart = -1;
							//neSeqStart = i;
							continue;
						} else if (i == end) { //  && neSeqStart != -1
							// remainder of non equal bits
							srcUnionInplaceAddFillUp(newList, parent,
									item.begin + end);
							//neSeqStart = -1;
						}

					}
					continue;
				}
			}
		}
		srcUnionInplaceAddFillUp(newList, parent, item.begin + item.width);
	}
	assert(newList.size());
	replacements = newList;
}

void VarBitConstraint::srcUnionInplaceAddFillUp(
		std::vector<KnownBitRangeInfo> &newList, const llvm::Value *parent,
		unsigned end) {

	unsigned lastEnd = 0;
	if (newList.size())
		lastEnd = newList.back().dstEndBitI();

	if (lastEnd != end) {
		assert(lastEnd < end);
		KnownBitRangeInfo kbri0(end - lastEnd);
		kbri0.src = parent;
		kbri0.srcBeginBitI = kbri0.dstBeginBitI = lastEnd;
		srcUnionPushBackWithMerge(newList, kbri0, 0, kbri0.width);
	}
}

void VarBitConstraint::srcUnionPushBackWithMerge(
		std::vector<KnownBitRangeInfo> &newList, KnownBitRangeInfo item,
		size_t srcOffset, size_t srcWidth) {
	assert(srcWidth > 0);
	assert(item.width >= srcWidth);
	assert(
			item.srcBeginBitI < item.src->getType()->getIntegerBitWidth()
					&& "bit range does not overflow");
	assert(
			item.srcBeginBitI + srcOffset + srcWidth
					<= item.src->getType()->getIntegerBitWidth()
					&& "bit range does not overflow");
	// select [srcOffset:srcOffset+srcWidth] bits from input item
	item.srcBeginBitI += srcOffset;
	item.dstBeginBitI += srcOffset;
	item.width = srcWidth;
	if (!newList.size()) {
		assert(item.dstBeginBitI == 0);
		newList.push_back(item);
		return; // nothing to merge
	}
	KnownBitRangeInfo &last = newList.back();
	if (auto *itemAsConst = dyn_cast<ConstantInt>(item.src)) {
		auto *lastAsConst = dyn_cast<ConstantInt>(last.src);
		if (lastAsConst) {
			assert(last.dstBeginBitI + last.width == item.dstBeginBitI);
			APInt v0(item.width + last.width, 0);
			APInt i0 = lastAsConst->getValue().lshr(last.srcBeginBitI).trunc(
					last.width).zext(v0.getBitWidth());
			APInt i1 = itemAsConst->getValue().lshr(item.srcBeginBitI).trunc(
					item.width).zext(v0.getBitWidth());
			assert(last.dstBeginBitI < item.dstBeginBitI);
			v0 = i0 | i1.shl(last.width);
			last.src = ConstantInt::get(last.src->getContext(), v0);
			last.width = v0.getBitWidth();
			last.srcBeginBitI = 0;
			return; // constants merged
		}
	} else if (isa<UndefValue>(item.src) && isa<UndefValue>(last.src)) {
		last.width += item.width;
		last.src = UndefValue::get(
				IntegerType::get(last.src->getContext(), last.width));
		last.srcBeginBitI = 0;
		return; // undefs merged
	}
	if (last.src == item.src
			&& last.srcBeginBitI + last.width == item.srcBeginBitI) {
		// if this item is just continuation of the previous slice
		assert(last.dstBeginBitI + last.width == item.dstBeginBitI);
		last.width += item.width;
		return; // merged into last
	}

	newList.push_back(item);
}

VarBitConstraint VarBitConstraint::slice(unsigned offset,
		unsigned width) const {
	assert(offset < 0xffff && width < 0xffff && "Sanity check");
	assert(width > 0);
	VarBitConstraint res(width);
	unsigned end = offset + width;
	assert(
			end <= useMask.getBitWidth()
					&& "Check if not selecting even more bits than it was in original non-reduced value");
	for (const KnownBitRangeInfo &i : replacements) {
		bool last = false;
		if (i.dstEndBitI() <= offset) {
			continue; // skip start
		} else if (i.dstBeginBitI < end) {
			if (i.dstBeginBitI < offset) {
				if (i.dstEndBitI() > end) {
					// must cut this item at the begin and end"
					res.replacements.push_back(
							i.slice(offset - i.dstBeginBitI, width));
					last = true;
				} else {
					// must cut this item at the begin
					auto o = offset - i.dstBeginBitI;
					res.replacements.push_back(i.slice(o, i.width - o));
				}
			} else if (i.dstEndBitI() > end) {
				// must cut this item at the end
				res.replacements.push_back(i.slice(0, end - i.dstBeginBitI));
				last = true;
			} else if (i.dstBeginBitI > end) {
				break;
			} else {
				// can add as is
				res.replacements.push_back(i);
			}
			assert(res.replacements.back().dstBeginBitI >= offset);
			res.replacements.back().dstBeginBitI -= offset;
			if (last) {
				break;
			}

		}
	}
	assert(res.consistencyCheck());
	return res;
}

void VarBitConstraint::substituteValue(const llvm::Value *oldV, llvm::Value *newV) {
	assert(newV->getType() == oldV->getType());
	for (auto &r : replacements) {
		if (r.src == oldV) {
			r.src = newV;
		}
	}
}

bool VarBitConstraint::isValue(const llvm::Value *V) const {
	if (replacements.size() == 1 && replacements[0].isValue(V))
		return true;
	else if (auto* VC = dyn_cast<CallInst>(V)) {
		return IsBitConcat(VC) && replacements == fromConcat(VC).replacements;
	}
	return false;
}

bool VarBitConstraint::consistencyCheck() const {
	if (!replacements.size())
		return false;
	if (replacements.back().dstEndBitI() != useMask.getBitWidth())
		return false;
	unsigned off = 0;
	for (const KnownBitRangeInfo &r : replacements) {
		if (r.dstBeginBitI != off)
			return false;
		off += r.width;
	}
	return true;
}

void VarBitConstraint::print(raw_ostream &O, bool IsForDebug) const {
	SmallString<40> UM;
	useMask.toString(UM, 16, /*isSigned*/false, /* formatAsCLiteral = */false);

	O << "{u: 0x" << UM << ", v:[";
	for (auto &src : replacements) {
		O << "    " << src << ", ";
	}
	O << "]}";
}
void VarBitConstraint::dump() const {
	print(dbgs(), true);
}

}
