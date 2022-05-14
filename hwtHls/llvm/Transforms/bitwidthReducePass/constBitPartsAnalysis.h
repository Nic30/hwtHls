#pragma once
#include "utils.h"
#include <map>
#include <set>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

/**
 * Visit all instructions and collect informations for constant propagation.
 */
class ConstBitPartsAnalysisContext {
protected:
	void visitBinaryOperatorReduceAnd(std::vector<KnownBitRangeInfo> &newParts,
			const llvm::BinaryOperator *parentI, unsigned width,
			unsigned dstOffset, const llvm::APInt &c,
			const KnownBitRangeInfo &v);
	void visitBinaryOperatorReduceOr(std::vector<KnownBitRangeInfo> &newParts,
			const llvm::BinaryOperator *parentI, unsigned width,
			unsigned dstOffset, const llvm::APInt &c,
			const KnownBitRangeInfo &v);

	// visit functions to discover which bits are constant in value
	// if value is of non int type the mask wit 1 bit is used
	VarBitConstraint& visitPHINode(const llvm::PHINode *I);
	VarBitConstraint& visitAsAllInputBitsUsedAllOutputBitsKnown(
			const llvm::Value *V);
	VarBitConstraint& visitInstruction(const llvm::Instruction *I);
	VarBitConstraint& visitConstantInt(const llvm::ConstantInt *CI);
	VarBitConstraint& visitSelectInst(const llvm::SelectInst *I);
	VarBitConstraint& visitBinaryOperator(const llvm::BinaryOperator *BO);
	VarBitConstraint& visitCmpInst(const llvm::CmpInst *I);
	VarBitConstraint& visitCallInst(const llvm::CallInst *V);
	VarBitConstraint& visitTrunc(const llvm::CastInst *I);
	VarBitConstraint& visitZExt(const llvm::CastInst *I);
	VarBitConstraint& visitSExt(const llvm::CastInst *I);

public:
	using InstructionToVarBitConstraintMap = std::map<const llvm::Value*, std::unique_ptr<VarBitConstraint>>;
	InstructionToVarBitConstraintMap constraints;
	ConstBitPartsAnalysisContext();
	VarBitConstraint& visitValue(const llvm::Value *V);
	// update constant bit info for instruction from dependencies, return true if changed
	bool updateInstruction(const llvm::Instruction *I);

};

}
