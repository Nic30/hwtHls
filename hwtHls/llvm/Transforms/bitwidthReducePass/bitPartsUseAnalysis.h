#pragma once
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>

#include <map>
#include <set>
#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/constBitPartsAnalysis.h>

namespace hwtHls {

class BitPartsUseAnalysisContext {
public:

	BitPartsConstraints &constraints;
	BitPartsUseAnalysisContext(BitPartsConstraints &constraints);
	// walk from user->def and propagate bits in VarBitConstraint.useMask

	// case where we do not have VarBitConstraint, all bits are thus used
	void updateUseMaskEntirelyUsed(const llvm::Value *V);
	void updateUseMaskEntirelyUsed(const llvm::Instruction *I);
	void updateUseMaskEntirelyUsedOperand(const llvm::Value *V);
	// case where we do have VarBitConstraint and we use it
	void updateUseMask(const llvm::Value *V, const llvm::APInt &newMask);
	void updateUseMask(const llvm::Value *V, VarBitConstraint &vbc,
			const llvm::APInt &newMask);
	void propagateUseMaskPHINode(const llvm::PHINode *I,
			const VarBitConstraint &vbc);
	void propageteUseMaskSelect(const llvm::SelectInst *I,
			const VarBitConstraint &vbc);
	void propagateUseMaskInstruction(const llvm::Instruction *I,
			const VarBitConstraint &vbc);
	void propagateUseMaskCallInst(const llvm::CallInst *C,
			const VarBitConstraint &vbc);
	void propagateUseMaskTrunc(const llvm::CastInst *I,
			const VarBitConstraint &vbc);
	void propagateUseMaskExt(const llvm::CastInst *I,
			const VarBitConstraint &vbc);

	std::optional<bool> getKnownBitBoolValue(const llvm::Value *V);
};

}
