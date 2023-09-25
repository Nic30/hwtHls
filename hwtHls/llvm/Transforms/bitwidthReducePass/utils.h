#pragma once
#include <vector>
#include <llvm/IR/Value.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

class KnownBitRangeInfo {
public:
	unsigned dstBeginBitI; // first bit in dst from where the value is set

	unsigned srcBeginBitI;
	unsigned srcWidth; // number of bits selected to this object, can be <= src->getType()->getBitWidth()
	const llvm::Value *src; // a value which is set to destination bit range

	KnownBitRangeInfo(unsigned bitwidth);
	KnownBitRangeInfo(const llvm::ConstantInt *CI);
	KnownBitRangeInfo(const llvm::Value *V);
	unsigned dstEndBitI() const;
	KnownBitRangeInfo slice(llvm::IRBuilder<> *Builder, unsigned offset,
			unsigned width) const;

	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
	bool operator!=(const KnownBitRangeInfo &rhs) const;
	bool operator==(const KnownBitRangeInfo &rhs) const;
};

struct UniqRangeSequence {
	// start/width specified for dst
	unsigned begin;
	unsigned width;
	const KnownBitRangeInfo *v0;
	const KnownBitRangeInfo *v1;
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
	llvm::APInt useMask; // mask of which bits are used from this value which bits are set during discovery process
	//// :note: this marks use of directly this instruction based on if the the input bit has effect on output

	std::vector<KnownBitRangeInfo> replacements;
	// non overlapping known values for bit ranges in this value, sorted lower bits first
	// if value is not specified this vector it means that the original bits of this value should be used

	// mask for each operand which is used to prune some bits from operand value
	// [todo] this is used only for compares, check it ti is required
	std::vector<llvm::APInt> operandUseMask;

	VarBitConstraint(unsigned bitWidth);
	VarBitConstraint(const llvm::ConstantInt *CI);
	VarBitConstraint(const llvm::Value *V);
	VarBitConstraint(const VarBitConstraint &obj);

	void addAllSetOperandMask(unsigned width);
	void clearAllOperandMasks(unsigned lowBitI, unsigned highBitI);
	// get mask for bits which are truly computed by this instruction
	// (are not known to be constant or some specific other value)
	llvm::APInt getTrullyComputedBitMask(const llvm::Value * selfValue) const;

	// fill known bit range as a slice on self
	//void _srcUnionInplaceSelf(const llvm::Value *parent, uint64_t offset,
	//		uint64_t width, std::vector<KnownBitRangeInfo> &newList);

	// parent is used to fill not known holes in bits when doing union
	// :param reduceUndefs: allow the output bits to take any other value for undef cases
	//       if false the undefs are treated as unique constant and it can not be merged with any other value
	//       than undef
	void srcUnionInplace(const VarBitConstraint &other,
			const llvm::Value *parent, bool reduceUndefs);

	// lowest first expected
	static void srcUnionInplaceAddFillUp(
			std::vector<KnownBitRangeInfo> &newList, const llvm::Value *parent,
			unsigned end);
	// lowest first expected
	// :param srcOffset: additional offset to current src offfset in item
	// :param srcWidth: width of added segment from item
	static void srcUnionPushBackWithMerge(
			std::vector<KnownBitRangeInfo> &newList, KnownBitRangeInfo item, size_t srcOffset, size_t srcWidth);
	VarBitConstraint slice(llvm::IRBuilder<> *Builder, unsigned offset,
			unsigned width) const;
	bool consystencyCheck() const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
};

}

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

