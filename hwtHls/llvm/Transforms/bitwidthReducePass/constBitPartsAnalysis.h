#pragma once
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>
#include <map>
#include <set>
#include <memory>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

class BitPartsConstraints {
	template<typename T_INSTR, typename T_VarBitConstraint_CONSTR_ARG>
	VarBitConstraint& _initConstraintMember(T_INSTR I, T_VarBitConstraint_CONSTR_ARG VarBitConstraint_constr_arg) {
		auto _C = std::make_unique<VarBitConstraint>(VarBitConstraint_constr_arg);
		VarBitConstraint &cur = *_C;
		constraints[I] = std::move(_C);
		return cur;
	}
public:
	BitPartsConstraints *parent;
	std::map<const llvm::Value*, std::unique_ptr<VarBitConstraint>> constraints;
	// delete copy constructor and = operator to prevent unintentional copy of "constraints" which contains unique pointers
	BitPartsConstraints (const BitPartsConstraints&) = delete;
	BitPartsConstraints& operator= (const BitPartsConstraints&) = delete;

	BitPartsConstraints(BitPartsConstraints *parent) :
			parent(parent) {
	}

	VarBitConstraint* findInConstraints(const llvm::Value *V);

	template<typename T>
	VarBitConstraint& initConstraintMember(T I) {
		auto _C = std::make_unique<VarBitConstraint>(I);
		VarBitConstraint &cur = *_C;
		constraints[I] = std::move(_C);
		return cur;
	}
	template<typename T>
	VarBitConstraint& initConstraintMember(T I, unsigned bitwidth) {
		return _initConstraintMember(I, bitwidth);
	}
	template<typename T>
	VarBitConstraint& initConstraintMember(T I, const llvm::ConstantInt* CI) {
		return _initConstraintMember(I, CI);
	}
	template<typename T>
	VarBitConstraint& initConstraintMember(T I, const llvm::Value* V) {
		return _initConstraintMember(I, V);
	}
	template<typename T>
	VarBitConstraint& initConstraintMember(T I, const VarBitConstraint& vbc) {
		return _initConstraintMember(I, vbc);
	}


	// get actual known value of a bit
	std::optional<bool> getKnownBitBoolValue(const llvm::Value *V);
	// :returns: the value which was previously set
	std::unique_ptr<VarBitConstraint> setKnownBitBoolValue(const llvm::Value *V,
			bool newV);
	virtual ~BitPartsConstraints(){}
};

/**
 * Visit all instructions and collect informations for constant propagation.
 */
class ConstBitPartsAnalysisContext: public BitPartsConstraints {
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
	virtual VarBitConstraint& visitSelectInst(const llvm::SelectInst *I);
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

	// if analysisHandle is specified and it returns the false the analysis ends there
	// and the value is used as is
	ConstBitPartsAnalysisContext(ConstBitPartsAnalysisContext *parent = nullptr,
			std::optional<std::function<bool(const llvm::Instruction&)>> analysisHandle =
					{ });

	void setShouldResolvePhiValues();
	VarBitConstraint& visitValue(const llvm::Value *V);
	// update constant bit info for instruction from dependencies, return true if changed
	bool updateInstruction(const llvm::Instruction *I);

	std::unique_ptr<ConstBitPartsAnalysisContext> createChild();
};

}
