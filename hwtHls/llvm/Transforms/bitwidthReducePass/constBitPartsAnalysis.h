#pragma once
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <map>
#include <set>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

/**
 * Visit all instructions and collect informations for constant propagation.
 */
class ConstBitPartsAnalysisContext {
protected:
	/*
	 * :param newParts: vector for newly generated value parts which is the result of this function
	 * :param width: width of parent instruction result
	 * :param dstOffset: offset in newly generated value
	 * :param vSrcOffset: bit offset in non constant operand value
	 * :param cSrcOffset: bit offset in constant operand value
	 * :param c: constant operand value
	 * :param v: non constant operand value
	 * */
	void visitBinaryOperatorReduceAnd(std::vector<KnownBitRangeInfo> &newParts,
			const llvm::BinaryOperator *parentI, unsigned width,
			unsigned vSrcOffset, unsigned cSrcOffset, unsigned dstOffset,
			const llvm::APInt &c, const KnownBitRangeInfo &v);
	void visitBinaryOperatorReduceOr(std::vector<KnownBitRangeInfo> &newParts,
			const llvm::BinaryOperator *parentI, unsigned width,
			unsigned vSrcOffset, unsigned cSrcOffset, unsigned dstOffset,
			const llvm::APInt &c, const KnownBitRangeInfo &v);

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

	std::optional<std::function<bool(const llvm::Instruction&)>> analysisHandle; // :see: constructor
	// if false phi replacement is resolved as PHI itself, if true
	// incoming values are used to resolve value for this PHI
	bool resolvePhiValues;
public:
	using InstructionToVarBitConstraintMap = std::map<const llvm::Value*, std::unique_ptr<VarBitConstraint>>;
	InstructionToVarBitConstraintMap constraints;

	// if analysisHandle is specified and it returns the false the analysis ends there
	// and the value is used as is
	ConstBitPartsAnalysisContext(
			std::optional<std::function<bool(const llvm::Instruction&)>> analysisHandle={});

	void setShouldResolvePhiValues();
	VarBitConstraint& visitValue(const llvm::Value *V);
	// update constant bit info for instruction from dependencies, return true if changed
	bool updateInstruction(const llvm::Instruction *I);

};

}
