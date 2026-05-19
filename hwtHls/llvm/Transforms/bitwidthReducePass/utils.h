#pragma once
#include <vector>
#include <llvm/IR/Value.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/IRBuilder.h>

#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>

namespace hwtHls {

class KnownBitRangeInfo {
public:
	unsigned dstBeginBitI; // first bit in dst from where the value is set

	unsigned srcBeginBitI;
	unsigned width; // number of bits selected to this object, can be <= src->getType()->getBitWidth()
	const llvm::Value *src; // a value which is set to destination bit range

	KnownBitRangeInfo(unsigned bitwidth);
	KnownBitRangeInfo(const llvm::ConstantInt *CI);
	KnownBitRangeInfo(const llvm::Value *V);
	KnownBitRangeInfo(const OffsetWidthValue &owv, unsigned dstBeginBitI);

	unsigned dstEndBitI() const;
	// check if this and itemOnRight overlaps in dst, if it is guaranteed this.begin <= itemOnRight.begin
	bool overlapsThisOnLeftInDst(const KnownBitRangeInfo &itemOnRight) const;
	// :note: It does not construct slices of values, srcBeginBitI and width is used in that case,
	//        constants are sliced immediately
	KnownBitRangeInfo slice(unsigned offset, unsigned width) const;

	llvm::APInt extractSelectedAPInt() const;

	// :returns: true if this record specifies exactly value V
	bool isValue(const llvm::Value *V) const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
	bool operator!=(const KnownBitRangeInfo &rhs) const;
	bool operator==(const KnownBitRangeInfo &rhs) const;
	bool isNegationOf(const KnownBitRangeInfo &other) const;
};

struct UniqRangeSequence {
	// start/width specified for dst
	unsigned begin;
	unsigned width;
	// :attention: v0 anv v1 are not strictly at the begin, but they
	//   are are known to define bits for range defined by this (the may be wider and shifted)
	const KnownBitRangeInfo *v0;
	const KnownBitRangeInfo *v1;

	llvm::APInt extractSelectedAPInt(const KnownBitRangeInfo *v) const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
	void dump() const;
};

class RangeSequenceIterator {
public:
	void appendNoCheck(std::vector<KnownBitRangeInfo>::const_iterator &v,
			unsigned vEnd, std::vector<UniqRangeSequence> &res, bool isV1);
	template<typename T>
	bool isInInterval(T left, T right, T point) {
		// left enclosed interval variant, point in? <left, right)
		return point >= left && point < right;
	}
	// :attention: this creates an unique intervals from two vectors of ranges,
	//  however the original src values presented in original ranges are not modified and
	//  may require some bit slicing to get the value actually specified by final range
	// :attention: ranges in input vec0 and vec1 may contain holes
	// :note: lowest bits first
	std::vector<UniqRangeSequence> uniqueRanges(
			const std::vector<KnownBitRangeInfo> &vec0,
			const std::vector<KnownBitRangeInfo> &vec1);
};


class VarBitConstraint {
public:
	// mask of which bits are used from this value which bits are set during discovery process
	//// :note: this marks use of directly this instruction based on if the the input bit has effect on output
	////        E.g. even if concat has useMask=0 it does not mean that bits in concat are unused, it means that the concat
	////        instruction itself does not compute any bits and src operands may still be important and used
	////        on places where the original concat instruction were used and the info about it is stored in replacements vector
	llvm::APInt useMask;

	// non overlapping known values for bit ranges in this value, sorted lower bits first
	// if value is not specified in this vector it means that the original bits of this value should be used
	std::vector<KnownBitRangeInfo> replacements;

	// mask for each operand which is used to prune some bits from operand value
	// :note: this is used only for compares, this is required because
	//   each operand have a different use mask in each cmp and this property is only
	//   way how to store this CmpInst private information
	// [todo] there are 2 same items in operandUseMask for CmpInst
	std::vector<llvm::APInt> operandUseMask;

	VarBitConstraint(unsigned bitWidth);
	VarBitConstraint(const llvm::ConstantInt *CI);
	VarBitConstraint(const llvm::Value *V);
	VarBitConstraint(const VarBitConstraint &obj);

	static VarBitConstraint fromConcat(const llvm::CallInst *V);
	static bool valuesHaveSameMeaning(const llvm::Value *V0,
			const llvm::Value *V1);
	bool _valuesHaveSameMeaning(const llvm::Value *V1) const;
	bool valuesHaveSameMeaning(const llvm::Value *V1) const;
	// returns true if all members are same and not undef
	bool replacementValuesEqual(const VarBitConstraint & other) const;
	// returns true if all there are known constant bits which do not equal
	// :attention: checks only for cases where replacements items have same width, if not returns false
	bool replacementValuesKnownNonEqualFast(const VarBitConstraint & other) const;
	const llvm::ConstantInt* tryGetConstantInt() const;
	
	
	// add all ones item into operandUseMask
	void addAllSetOperandMask(unsigned width);
	void clearAllOperandMasks();
	void clearAllOperandMasks(unsigned lowBitI, unsigned highBitI);
	// get mask for bits which are truly computed by this instruction
	// (are not known to be constant or some specific other value)
	llvm::APInt getTrullyComputedBitMask(const llvm::Value *selfValue) const;

	// prune all bits in useMask which are 0
	VarBitConstraint toAllOnesUseMask() const;
	// fill known bit range as a slice on self
	//void _srcUnionInplaceSelf(const llvm::Value *parent, uint64_t offset,
	//		uint64_t width, std::vector<KnownBitRangeInfo> &newList);

	// Merge with "other" same bits will remain same, different bits will be set to slice from "parent"
	// parent is used to fill not known holes in bits when doing union
	// :param reduceUndefs: allow the output bits to take any other value for undef cases
	//       if false the undefs are treated as unique constant and it can not be merged with any other value
	//       except for another undef
	void srcUnionInplace(const VarBitConstraint &other,
			const llvm::Value *parent, bool reduceUndefs);

	struct DetectBitsDrivenByConditionResultItem {
		std::optional<bool> isDrivenByCondWithPolarity; // true if specified bits are driven by Cond, false if by ~Cond and noopt if something else
		std::optional<bool> knownConst; // specifies if bit is known to be 0/1
		unsigned dstBeginBitI; // first bit in dst from where the value is set
		unsigned bitWidth; // the length of described bit sequence
	};
	/*
	 * :param bitsDrivenByC: output vector for information about bits of SelectInst like instruction
	 * :note: bitsDrivenByC is sparse, it contains items only for bits which were resolved to have isDrivenByCondWithPolarity/knownConst
	 * */
	static void detectBitsDrivenByCondition(const VarBitConstraint &Cond,
			const VarBitConstraint &TrueVal, const VarBitConstraint &FalseVal,
			llvm::SmallVector<DetectBitsDrivenByConditionResultItem> &bitsDrivenByC);

	// update replacements and useMask from result of detectBitsDrivenByCondition
	void mergeWithBitsDrivenByCondition(llvm::LLVMContext &Ctx,
			llvm::ArrayRef<DetectBitsDrivenByConditionResultItem> bitsDrivenByC,
			const KnownBitRangeInfo &Cond, const KnownBitRangeInfo *Cond_n);

	// lowest first expected
	static void srcUnionInplaceAddFillUp(
			std::vector<KnownBitRangeInfo> &newList, const llvm::Value *parent,
			unsigned end);
	// lowest first expected
	// :param srcOffset: additional offset to current src offfset in item
	// :param srcWidth: width of added segment from item
	static void srcUnionPushBackWithMerge(
			std::vector<KnownBitRangeInfo> &newList, KnownBitRangeInfo item,
			size_t srcOffset, size_t srcWidth);
	VarBitConstraint slice(unsigned offset, unsigned width) const;
	// replace value in every member of replacements vector
	void substituteValue(const llvm::Value *oldV, llvm::Value *newV);
	// :returns: true if this record equals exactly to just value V
	bool isValue(const llvm::Value *V) const;

	bool consistencyCheck() const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
	void dump() const;
	bool operator==(const KnownBitRangeInfo &other) const;
	bool isNegationOf(const VarBitConstraint &other) const;
	bool isNegationOf(const KnownBitRangeInfo &other) const;
};

}

namespace llvm {

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::KnownBitRangeInfo &V) {
	V.print(OS);
	return OS;
}

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::VarBitConstraint &V) {
	V.print(OS);
	return OS;
}

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::UniqRangeSequence &V) {
	V.print(OS);
	return OS;
}

}
