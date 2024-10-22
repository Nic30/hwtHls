#pragma once
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <llvm/ADT/SetVector.h>
#include <list>
#include <set>

namespace hwtHls {

/**
 * This class can used to discover if PHINode bits contain some specific value
 *
 * We can not simply loop at the operands and check for matching bits as in case of SelectInst
 * because PHI may use itself with arbitrary shift.
 * This complicates the prove of some bits having some exact value because
 * values may rotate in PHI.
 *
 * We have to build an info about which possible values may appear on each bit from every input value.
 * First we initialize it with replacement values from all input values.
 * Then we iteratively propagate values to bit which are using them until total PHI value
 * does not change or we know that every bit may have multiple values
 * (The PHI itself, no matter the slice, is not counted in this number) and thus it can not be extracted.
 */
class PHIValueProover {
protected:
	const llvm::PHINode *phi;
	// A record used to hold info about bits in phi
	class ValueInfo {
	public:
		// true if this value is know to have multiple distinct values and thus it can not be reduced
		// :note: values referring to phi are not counted as distinct values and thus knownToBe.size() > 0 && !hasMultipleValues
		// :note: once hasMultipleValues is set any item to knownToBe is not added, to spare memory if we know that this chunk will
		//        not be optimized out
		// :note: if this is true currentValue is {}
		bool hasMultipleValues;

		std::optional<KnownBitRangeInfo> currentValue;

		size_t width; // if width == 0 this record is invalid and it is placeholder for possible future record
		// Set of offset of phi slices which may appear at this bit slice
		// :note: required because we need to propagate split points in both directions
		std::set<size_t> phiDeps;

		// used when the value changes to broadcast to all users
		// :note: if ValueInfo is split, the split propagates on all deps and users, so all of them have same width
		std::set<size_t> users;
		ValueInfo();
		ValueInfo(size_t width);
		ValueInfo(const llvm::PHINode *phi, const KnownBitRangeInfo &kbri);
	};
	// vector of size of width with record for all bits in phi
	std::vector<ValueInfo> knownBits;
	using KnownBitsIteraor = typename std::vector<ValueInfo>::iterator;
	// append to knownToBe item under valInfoIt
	// :attention: This updates flags in ValueInfo and may add items into knownToBe
	void knownBits_insertSameSize(KnownBitsIteraor valInfoIt,
			const KnownBitRangeInfo &kbri, bool hasMultipleValues=false);
	void knownBits_insertSameSizePhi(KnownBitsIteraor valInfoIt,
				const KnownBitRangeInfo &kbri, bool hasMultipleValues);
	// :note: if hasMultipleValues=true the values can not be split
	//        if it is constant the split may happen if the current value is not entirely same but has some same bits
	//        if it is phi the split may happen if referenced phi segment is smaller or wider
	void knownBits_insertSameSizeNonPhi(KnownBitsIteraor valInfoIt,
			const KnownBitRangeInfo *kbri, bool hasMultipleValues);
	void knownBits_insert(const KnownBitRangeInfo &kbri);
	// splits item in knownBits into two, width of first one will be newWidthOfLeft
	void knownBits_splitItem(KnownBitsIteraor knownBitsItem,
			size_t newWidthOfLeft);

public:
	PHIValueProover(const llvm::PHINode *phi);
	void addOperandConstraint(const VarBitConstraint &opConstr);
	VarBitConstraint resolve();

	bool consistencyCheck() const;
	void print(llvm::raw_ostream &O, bool IsForDebug = false) const;
};

}

inline llvm::raw_ostream& operator<<(llvm::raw_ostream &OS,
		const hwtHls::PHIValueProover &V) {
	V.print(OS);
	return OS;
}
