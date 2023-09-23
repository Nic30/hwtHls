#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>


using namespace llvm;
namespace hwtHls {

KnownBitRangeInfo::KnownBitRangeInfo(unsigned bitwidth) :
		dstBeginBitI(0), srcBeginBitI(0), srcWidth(bitwidth), src(nullptr) {
}
KnownBitRangeInfo::KnownBitRangeInfo(const ConstantInt *CI) :
		dstBeginBitI(0), srcBeginBitI(0), srcWidth(CI->getBitWidth()), src(CI) {
}
KnownBitRangeInfo::KnownBitRangeInfo(const Value *V) :
		dstBeginBitI(0), srcBeginBitI(0), srcWidth(
				V->getType()->isIntegerTy() ?
						V->getType()->getIntegerBitWidth() : 1), src(V) {
}

unsigned KnownBitRangeInfo::dstEndBitI() const {
	return dstBeginBitI + srcWidth;
}

KnownBitRangeInfo KnownBitRangeInfo::slice(IRBuilder<> *Builder,
		unsigned offset, unsigned width) const {
	assert(offset < 0xffff && width < 0xffff);
	assert(width > 0);
	KnownBitRangeInfo res(width);
	if (auto *CI = dyn_cast<const ConstantInt>(src)) {
		auto v = CI->getValue();
		v.lshrInPlace(offset);
		assert(res.srcBeginBitI == 0);
		res.src = Builder->getInt(v.trunc(width));
		res.srcBeginBitI = 0;
	} else {
		res.src = src;
		res.srcBeginBitI = srcBeginBitI + offset;
	}
	res.dstBeginBitI = dstBeginBitI + offset;
	return res;
}

void KnownBitRangeInfo::print(raw_ostream &O, bool IsForDebug) const {
	O << "[" << (dstBeginBitI + srcWidth) << ":" << dstBeginBitI << "]=(";
	if (dyn_cast<ConstantInt>(src)) {
		O << *src;
	} else {
		if (src->hasName())
			O << "%" << src->getName();
		else {
			O << "%" << src;
		}
	}
	O << ")[" << (srcBeginBitI + srcWidth) << ":" << srcBeginBitI << "]";
}
bool KnownBitRangeInfo::operator!=(const KnownBitRangeInfo &rhs) const {
	return (dstBeginBitI != rhs.dstBeginBitI || srcBeginBitI != rhs.srcBeginBitI
			|| srcWidth != rhs.srcWidth || src != rhs.src);
}
bool KnownBitRangeInfo::operator==(const KnownBitRangeInfo &rhs) const {
	return (dstBeginBitI == rhs.dstBeginBitI && srcBeginBitI == rhs.srcBeginBitI
			&& srcWidth == rhs.srcWidth && src == rhs.src);
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
	unsigned end = v->srcWidth - previouslyConsummedBits;
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
		useMask(obj.useMask), replacements(obj.replacements) {
}
void VarBitConstraint::addAllSetOperandMask(unsigned width) {
	operandUseMask.push_back(APInt::getAllOnesValue(width));
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
	APInt m(useMask.getBitWidth(), 0);
	for (const KnownBitRangeInfo &r : replacements) {
		if (!dyn_cast<ConstantInt>(r.src) && r.src == selfValue) {
			m.setBits(r.dstBeginBitI, r.dstBeginBitI + r.srcWidth);
		}
	}
	return m;
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
		const llvm::Value *parent) {
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
			if (isa<UndefValue>(item.v0->src)) {
				srcUnionPushBackWithMerge(newList, *item.v1,
						item.begin - item.v1->dstBeginBitI, item.width);
				continue;
			} else if (isa<UndefValue>(item.v1->src)) {
				srcUnionPushBackWithMerge(newList, *item.v0,
						item.begin - item.v0->dstBeginBitI, item.width);
				continue;
			} else if (item.v0->src == item.v1->src
					&& item.v0->dstBeginBitI - item.v0->srcBeginBitI == item.v1->dstBeginBitI - item.v1->srcBeginBitI) {
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
									kbri.srcWidth);
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
		srcUnionPushBackWithMerge(newList, kbri0, 0, kbri0.srcWidth);
	}
}

void VarBitConstraint::srcUnionPushBackWithMerge(
		std::vector<KnownBitRangeInfo> &newList, KnownBitRangeInfo item,
		size_t srcOffset, size_t srcWidth) {
	assert(srcWidth > 0);
	assert(item.srcWidth >= srcWidth);
	assert(
			item.srcBeginBitI + srcOffset + srcWidth
					<= item.src->getType()->getIntegerBitWidth());
	// select [srcOffset:srcOffset+srcWidth] bits from input item
	item.srcBeginBitI += srcOffset;
	item.dstBeginBitI += srcOffset;
	item.srcWidth = srcWidth;
	if (!newList.size()) {
		assert(item.dstBeginBitI == 0);
		newList.push_back(item);
		return; // nothing to merge
	}
	KnownBitRangeInfo &last = newList.back();
	if (auto *itemAsConst = dyn_cast<ConstantInt>(item.src)) {
		auto *lastAsConst = dyn_cast<ConstantInt>(last.src);
		if (lastAsConst) {
			assert(last.dstBeginBitI + last.srcWidth == item.dstBeginBitI);
			APInt v0(item.srcWidth + last.srcWidth, 0);
			APInt i0 = lastAsConst->getValue().lshr(last.srcBeginBitI).trunc(
					last.srcWidth).zext(v0.getBitWidth());
			APInt i1 = itemAsConst->getValue().lshr(item.srcBeginBitI).trunc(
					item.srcWidth).zext(v0.getBitWidth());
			assert(last.dstBeginBitI < item.dstBeginBitI);
			v0 = i0 | i1.shl(last.srcWidth);
			last.src = ConstantInt::get(last.src->getContext(), v0);
			last.srcWidth = v0.getBitWidth();
			last.srcBeginBitI = 0;
			return; // constants merged
		}
	} else if (isa<UndefValue>(item.src) && isa<UndefValue>(last.src)) {
		last.srcWidth += item.srcWidth;
		last.src = UndefValue::get(
				IntegerType::get(last.src->getContext(), last.srcWidth));
		last.srcBeginBitI = 0;
		return; // undefs merged
	}
	if (last.src == item.src
			&& last.srcBeginBitI + last.srcWidth == item.srcBeginBitI) {
		// if this item is just continuation of the previous slice
		assert(last.dstBeginBitI + last.srcWidth == item.dstBeginBitI);
		last.srcWidth += item.srcWidth;
		return; // merged into last
	}

	newList.push_back(item);
}

VarBitConstraint VarBitConstraint::slice(IRBuilder<> *Builder, unsigned offset,
		unsigned width) const {
	assert(offset < 0xffff && width < 0xffff);
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
							i.slice(Builder, offset - i.dstBeginBitI, width));
					last = true;
				} else {
					// must cut this item at the begin
					auto o = offset - i.dstBeginBitI;
					res.replacements.push_back(
							i.slice(Builder, o, i.srcWidth - o));
				}
			} else if (i.dstEndBitI() > end) {
				// must cut this item at the end
				res.replacements.push_back(
						i.slice(Builder, 0, end - i.dstBeginBitI));
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
	assert(res.consystencyCheck());
	return res;
}

bool VarBitConstraint::consystencyCheck() const {
	if (!replacements.size())
		return false;
	if (replacements.back().dstEndBitI() != useMask.getBitWidth())
		return false;
	unsigned off = 0;
	for (const KnownBitRangeInfo &r : replacements) {
		if (r.dstBeginBitI != off)
			return false;
		off += r.srcWidth;
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
}
