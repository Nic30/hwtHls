#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <llvm/ADT/SmallString.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/Transforms/utils/bitWidthInfo.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

KnownBitRangeInfo::KnownBitRangeInfo(unsigned bitwidth) :
		dstBeginBitI(0), srcBeginBitI(0), width(bitwidth), src(nullptr) {
}
KnownBitRangeInfo::KnownBitRangeInfo(const ConstantInt *CI) :
		dstBeginBitI(0), srcBeginBitI(0), width(CI->getBitWidth()), src(CI) {
}
KnownBitRangeInfo::KnownBitRangeInfo(const Value *V) :
		dstBeginBitI(0), srcBeginBitI(0), width(getIntegerBitWidthOr1(V)), src(
				V) {
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
			srcBeginBitI + offset + width <= getIntegerBitWidthOr1(src)
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
	if (isa<ConstantData>(src)) {
		O << *src;
	} else if (src->hasName()) {
		O << "%" << src->getName();
	} else {
		O << src; // print pointer
	}
	O << ")[" << (srcBeginBitI + width) << ":" << srcBeginBitI << "]";
}
bool KnownBitRangeInfo::operator!=(const KnownBitRangeInfo &rhs) const {
	return (dstBeginBitI != rhs.dstBeginBitI || srcBeginBitI != rhs.srcBeginBitI
			|| width != rhs.width || src != rhs.src);
}
bool KnownBitRangeInfo::operator==(const KnownBitRangeInfo &rhs) const {
	if (dstBeginBitI == rhs.dstBeginBitI && srcBeginBitI == rhs.srcBeginBitI
			&& width == rhs.width && src == rhs.src) {
		return true;
	}
	return false;
}

bool KnownBitRangeInfo::isNegationOf(const KnownBitRangeInfo &rhs) const {
	if (dstBeginBitI != rhs.dstBeginBitI || srcBeginBitI != rhs.srcBeginBitI
			|| width != rhs.width) {
		return false;
	}
	// handle commutativity
	std::array<std::pair<const Value*, const Value*>, 2> values;
	values[0] = { src, rhs.src };
	values[1] = { rhs.src, src };
	for (const auto& [src0, src1] : values) {
		if (match(src0, m_Not(m_Specific(src1)))) {
			return true;
		}

		Value *LHS0, *RHS0;
		CmpPredicate P0, P1;
		if (width == 1 && match(src0, m_Cmp(P0, m_Value(LHS0), m_Value(RHS0)))) {
			Value *LHS1, *RHS1;
			if (match(src1, m_Cmp(P1, m_Value(LHS1), m_Value(RHS1)))) {
				if (CmpInst::getInversePredicate(P0) == P1) {
					// e.g. a == b is negation of a != b
					return LHS0 == LHS1 && RHS0 == RHS1;
				} else if (CmpInst::getSwappedPredicate(P0)
						== CmpInst::getInversePredicate(P1)) {
					if (LHS0 == RHS0 && LHS0 == LHS1 && RHS0 == RHS1)
						// e.g. a == a is negation of a != a
						return true;
					if (LHS0 == RHS1 && RHS0 == LHS1)
						// e.g. a < b is negation of !(b >= a) === (b < a)
						return true;
				}
			}
		}
	}
	return false;
}

llvm::APInt UniqRangeSequence::extractSelectedAPInt(
		const KnownBitRangeInfo *v) const {
	assert(v == v0 || v == v1);
	auto _v = dyn_cast<ConstantInt>(v->src);
	assert(_v);
	assert(begin >= v->dstBeginBitI);
	// prepare values exactly selected by this item
	return _v->getValue().extractBits(width,
			v->srcBeginBitI + (begin - v->dstBeginBitI));
}

void UniqRangeSequence::print(llvm::raw_ostream &O, bool IsForDebug) const {
	O << "<UniqRangeSequence begin:" << begin << ", width:" << width << " [";
	if (v0) {
		O << *v0 << ", ";
	} else {
		O << "nullptr, ";
	}
	if (v1) {
		O << *v1 << "]>";
	} else {
		O << "nullptr]>";
	}
}

void UniqRangeSequence::dump() const {
	print(dbgs());
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
		useMask(getIntegerBitWidthOr1(V), 0) {
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
					dstOffset = newParts.back().dstBeginBitI
							+ newParts.back().width;
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

bool VarBitConstraint::valuesHaveSameMeaning(const llvm::Value *V0,
		const llvm::Value *V1) {
	if (V0 == V1)
		return true;
	if (V0->getType() != V1->getType())
		return false;
	if (auto V0C = dyn_cast<CallInst>(V0)) {
		if (auto V1C = dyn_cast<CallInst>(V1)) {
			if (IsBitConcat(V0C) && IsBitConcat(V1C)) {
				return fromConcat(V0C).replacements
						== fromConcat(V1C).replacements;
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
		hasSameWidth = useMask.getBitWidth() == getIntegerBitWidthOr1(V1);
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
		else if (useMask.popcount() != getIntegerBitWidthOr1(V1)) {
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
	size_t w = operandUseMask[0].getBitWidth();
	APInt m = ~APInt::getBitsSet(w, lowBitI, highBitI);
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
	for (const auto &r : replacements) {
		auto useM = useMask.extractBits(r.width, r.dstBeginBitI);
		if (useM.isAllOnes())
			res.replacements.push_back(r);
		else {
			iterUsedBitRangeSlices(useM,
					[&res, &r](size_t offset, size_t width) {
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
				if (isa<ConstantInt>(item.v0->src)
						&& isa<ConstantInt>(item.v1->src)) {
					// prepare values exactly selected by this item
					auto v0 = item.extractSelectedAPInt(item.v0);
					auto v1 = item.extractSelectedAPInt(item.v1);
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

void VarBitConstraint::mergeWithBitsDrivenByCondition(llvm::LLVMContext &Ctx,
		llvm::ArrayRef<VarBitConstraint::DetectBitsDrivenByConditionResultItem> bitsDrivenByC,
		const KnownBitRangeInfo &Cond, const KnownBitRangeInfo *Cond_n) {
	if (bitsDrivenByC.empty())
		return;

	KnownBitRangeInfo kbri(1);
	auto update = bitsDrivenByC.begin();
	std::vector<KnownBitRangeInfo> newReplacements;
	newReplacements.reserve(replacements.size() + bitsDrivenByC.size());
	auto rIt = replacements.begin();
	// errs() << "updates: ";
	// for (auto u : bitsDrivenByC) {
	// 	errs() << " update: " << u.isDrivenByCondWithPolarity << " "
	// 			<< u.knownConst << " " << u.dstBeginBitI << " " << u.bitWidth
	// 			<< "\n";
	// }
	// iterate replacements and bitsDrivenByC at once and merge these sparse sequences which are
	// defining knowledge about bits of value for which is this object created
	for (; rIt != replacements.end() || update != bitsDrivenByC.end();) {
		assert(
				update == bitsDrivenByC.end()
						|| update->isDrivenByCondWithPolarity.has_value()
						|| update->knownConst.has_value());
		//errs() << "mergeWithBitsDrivenByCondition: r:";
		//if (rIt != replacements.end()) {
		//	errs() << *rIt << " ";
		//}
		//if (update != bitsDrivenByC.end()) {
		//	errs() << " update: " << update->isDrivenByCondWithPolarity << " "
		//			<< update->knownConst << " " << update->dstBeginBitI << " "
		//			<< update->bitWidth;
		//}
		//errs() << "\n";

		if (update == bitsDrivenByC.end()
				|| (rIt != replacements.end()
						&& update->dstBeginBitI
								>= rIt->dstBeginBitI + rIt->width)) {
			// no other pending update or update is after this item from replacements
			newReplacements.push_back(*rIt);
			++rIt;
			continue;
		}
		if (update->knownConst.has_value()) {
			kbri = KnownBitRangeInfo(
					update->knownConst.value() ?
							ConstantInt::getTrue(Ctx) :
							ConstantInt::getFalse(Ctx));
		} else if (update->isDrivenByCondWithPolarity.has_value()) {
			kbri = update->isDrivenByCondWithPolarity.value() ? Cond : *Cond_n; // intentional copy
		} else {
			llvm_unreachable(
					"This case should have been filtered at the begin of this loop");
		}
		kbri.dstBeginBitI = update->dstBeginBitI;
		assert(kbri.width == 1);
		useMask.clearBit(kbri.dstBeginBitI);
		for (auto &m : operandUseMask) {
			m.clearBit(kbri.dstBeginBitI);
		}
		if (rIt == replacements.end()
				|| kbri.dstBeginBitI < rIt->dstBeginBitI) {
			// no remaining item in replacements or the item is after this update
			newReplacements.push_back(kbri);
			++update;
			continue;
		}
		const auto &r = *rIt;
		assert(
				update->dstBeginBitI >= r.dstBeginBitI
						&& update->dstBeginBitI < r.dstBeginBitI + r.width
						&& "new update is somewhere in current replacement item");
		// now we found item r in replacements which is on position requested by update

		// if bit is in range defined by this item
		if (r.width == 1) {
			// r is exactly of the size of kbri
			newReplacements.push_back(kbri);
			++rIt;
		} else if (r.dstBeginBitI == kbri.dstBeginBitI) {
			// kbri begin on first bit of r
			newReplacements.push_back(kbri);
			*rIt = r.slice(1, r.width - 1);
			// newReplacements.push_back(*rIt); // this will be done later as we do not increment rIt
		} else if (r.dstBeginBitI + r.width - 1 == kbri.dstBeginBitI) {
			// kbri begin on last bit of r
			auto r0 = r.slice(0, r.width - 1);
			newReplacements.push_back(r0);
			newReplacements.push_back(kbri);
			++rIt;
		} else {
			// kbri begin is in the middle of r
			auto prefixWidth = kbri.dstBeginBitI - r.dstBeginBitI;
			auto r0 = r.slice(0, prefixWidth);
			*rIt = r.slice(prefixWidth + 1, r.width - prefixWidth - 1);
			newReplacements.push_back(r0);
			newReplacements.push_back(kbri);
			// newReplacements.push_back(*rIt); // this will be done later as we do not increment rIt
		}
		assert(kbri.width == 1);
		update++;
	}
	assert(update == bitsDrivenByC.end());
	replacements = newReplacements;
}

void VarBitConstraint::detectBitsDrivenByCondition(const VarBitConstraint &Cond,
		const VarBitConstraint &TrueVal, const VarBitConstraint &FalseVal,
		llvm::SmallVector<DetectBitsDrivenByConditionResultItem> &bitsDrivenByC) {
	RangeSequenceIterator rsa;
	assert(TrueVal.replacements.size());
	assert(FalseVal.replacements.size());
	for (const auto &item : rsa.uniqueRanges(TrueVal.replacements,
			FalseVal.replacements)) {
		auto v0 = item.v0->slice(item.begin - item.v0->dstBeginBitI,
				item.width);
		auto v1 = item.v1->slice(item.begin - item.v1->dstBeginBitI,
				item.width);
		assert(v0.dstBeginBitI == v1.dstBeginBitI);
		auto v0IsC = isa<ConstantInt>(v0.src);
		auto v1IsC = isa<ConstantInt>(v1.src);
		// if T == 1 or T == C and F == 0 or F == ~C
		// then the bit is driven directly by Cond

		// if sequence length is > 1 instead of C we should compare with sext C

		// :note: items in uniqueRanges are split in a way which makes Cond be to always appear only once in item
		//  this means that we do not need to iterate over all bits of the item to find C or !C
		if (v0IsC) {
			auto v0C = item.extractSelectedAPInt(item.v0);

			if (v1IsC) {
				// both constants iterate individual bits
				auto v1C = item.extractSelectedAPInt(item.v1);
				//errs() << "detectBitsDrivenByCondition: " << v0C << "  " << v1C
				//		<< " width: " << item.width << "\n";
				for (unsigned bitI = 0; bitI != item.width; bitI++) {
					auto tBit = v0C[bitI];
					auto fBit = v1C[bitI];
					std::optional<bool> condAsBitPolarity = { };
					if (tBit && !fBit) {
						// T == 1, F == 0 ==> C
						condAsBitPolarity = true;
					} else if (!tBit && fBit) {
						// T == 0, F == 1 ==> ~C
						condAsBitPolarity = false;
					}
					// :attention: the cases of same values are not detected as this function detects only special
					// cases related to Cond, and all other cases would be already known
					if (condAsBitPolarity.has_value())
						bitsDrivenByC.push_back(
								{ condAsBitPolarity, { }, v0.dstBeginBitI
										+ bitI, 1 });
				}
			} else {
				//errs() << "detectBitsDrivenByCondition: " << v0C << "  " << v1
				//		<< "\n";
				// only v0 is const, v1 can still be C or ~C
				if (item.width == 1) {
					auto tBit = v0C[0];
					auto &fBit = v1;

					std::optional<bool> condAsBitPolarity = { };
					std::optional<bool> knownConst = { };
					if (fBit == Cond) {
						if (tBit) {
							// T == 1, F == C (==0) ==> C
							condAsBitPolarity = true;
						} else {
							// T == 0, F == C (==0) ==> 0
							knownConst = false;
						}
					} else if (Cond.isNegationOf(fBit)) {
						if (tBit) {
							// T == 1, F == !C (==1) ==> 1
							knownConst = true;
						} else {
							// T == 0, F == !C (==1) ==> !C
							condAsBitPolarity = false;
						}
					}
					if (condAsBitPolarity.has_value() || knownConst.has_value())
						bitsDrivenByC.push_back(
								{ condAsBitPolarity, { }, v0.dstBeginBitI, 1 });
				}
			}
		} else {
			if (v1IsC) {
				// only v1 is const, v0 can still be C or ~C
				auto v1C = item.extractSelectedAPInt(item.v1);
				//errs() << "detectBitsDrivenByCondition: " << v0 << "  " << v1C
				//		<< "\n";
				if (item.width == 1) {
					auto &tBit = v0;
					auto fBit = v1C[0];

					std::optional<bool> condAsBitPolarity = { };
					std::optional<bool> knownConst = { };
					if (tBit == Cond) {
						if (fBit) {
							// T == C (==1), F == 1 ==> 1
							knownConst = true;
						} else {
							// T == C (==1), F == 0 ==> C
							condAsBitPolarity = true;
						}
					} else if (Cond.isNegationOf(tBit)) {
						if (fBit) {
							// T == !C (==0), F == 1 ==> !C
							condAsBitPolarity = false;
						} else {
							// T == !C (==0), F == 0 ==> 0
							knownConst = true;
						}
					}
					if (condAsBitPolarity.has_value() || knownConst.has_value())
						bitsDrivenByC.push_back(
								{ condAsBitPolarity, { }, v0.dstBeginBitI, 1 });
				}
			} else {
				//errs() << "detectBitsDrivenByCondition: " << v0 << "  "
				//		<< *item.v1 << "\n";
				// v0, v1 can still be C or ~C
				if (item.width == 1) {
					// the items should be split on smallest
					auto &tBit = v0;
					auto &fBit = v1;
					std::optional<bool> condAsBitPolarity = { };
					std::optional<bool> knownConst = { };
					if (tBit == Cond) {
						if (fBit == Cond) {
							// T == C (==1), F == C (==0) ==> 1
							knownConst = true;
						} else if (Cond.isNegationOf(fBit)) {
							// T == C (==1), F == !C (==1) ==> C
							condAsBitPolarity = true;
						}
					} else if (Cond.isNegationOf(tBit)) {
						if (fBit == Cond) {
							// T == !C (==0), F == C (==0) ==> 0
							knownConst = false;
						} else if (Cond.isNegationOf(fBit)) {
							// T == !C (==0), F == !C (==1) ==> !C
							condAsBitPolarity = false;
						}
					}
					if (condAsBitPolarity.has_value() || knownConst.has_value())
						bitsDrivenByC.push_back(
								{ condAsBitPolarity, { }, v0.dstBeginBitI, 1 });
				}
			}
		}
	}
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
#ifndef NDEBUG
	size_t srcTWidth = getIntegerBitWidthOr1(item.src);
	assert(item.srcBeginBitI < srcTWidth && "bit range does not overflow");
	assert(
			item.srcBeginBitI + srcOffset + srcWidth <= srcTWidth
					&& "bit range does not overflow");
#endif
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

void VarBitConstraint::substituteValue(const llvm::Value *oldV,
		llvm::Value *newV) {
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
	else if (auto *VC = dyn_cast<CallInst>(V)) {
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
	if (operandUseMask.size()) {
		O << ", opUse:[";
		for (auto &ou : operandUseMask) {
			SmallString<40> UM;
			ou.toString(UM, 16, /*isSigned*/false, /* formatAsCLiteral = */
			false);
			O << "0x" << UM << ",";
		}
		O << "]";
	}
	O << "]}";
}

void VarBitConstraint::dump() const {
	print(dbgs(), true);
	dbgs() << "\n";
}

bool VarBitConstraint::operator==(const KnownBitRangeInfo &other) const {
	return replacements.size() == 1 && replacements[0] == other;
}

bool VarBitConstraint::isNegationOf(const VarBitConstraint &other) const {
	if (replacements.size() != other.replacements.size())
		return false;
	for (const auto& [r0, r1] : zip(replacements, other.replacements)) {
		if (!r0.isNegationOf(r1))
			return false;
	}
	return true;
}
bool VarBitConstraint::isNegationOf(const KnownBitRangeInfo &other) const {
	return replacements.size() == 1 && replacements[0].isNegationOf(other);
}

}
