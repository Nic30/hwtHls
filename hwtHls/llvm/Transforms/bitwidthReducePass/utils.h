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
	unsigned srcWidth; // can be <= src->getType()->getBitWidth()
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
	std::vector<UniqRangeSequence> uniqueRanges(
			const std::vector<KnownBitRangeInfo> &vec0,
			const std::vector<KnownBitRangeInfo> &vec1);

};

class VarBitConstraint {
public:
	llvm::APInt useMask; // mask of which bits are used from this value which bits are set during discovery process
	//std::vector<llvm::APInt> opUseMask; // mask describing which bits are actually used from an operand by this operator
	//// if the bit from operand is used depends on instruction e.g. for PHINode bit is used if it has a different value
	//// at least in single operand
	//// :note: this marks use directly this operator based on if the the input bit has effect on output

	std::vector<KnownBitRangeInfo> replacements;
	// non overlapping known values for bit ranges in this value, sorted lower bits first
	// if value is not specified this vector it means that the original bits of this value should be used

	// mask for each operand which is used to prune some bits from operand value
	std::vector<llvm::APInt> operandUseMask;
	VarBitConstraint(unsigned bitWidth);
	VarBitConstraint(const llvm::ConstantInt *CI);
	VarBitConstraint(const llvm::Value *V);
	VarBitConstraint(const VarBitConstraint &obj);

	void addAllSetOperandMask(unsigned width);
	void clearAllOperandMasks(unsigned lowBitI, unsigned highBitI);
	llvm::APInt getNonConstBitMask() const;

	// parent is used to fill not known holes in bits when doing union
	void srcUnionInplace(const VarBitConstraint &other,
			const llvm::Value *parent);
	// lowest first expected
	static void srcUnionInplaceAddFillUp(
			std::vector<KnownBitRangeInfo> &newList, const llvm::Value *parent,
			unsigned end);
	// lowest first expected
	static void srcUnionPushBackWithMerge(
			std::vector<KnownBitRangeInfo> &newList, KnownBitRangeInfo item);
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
