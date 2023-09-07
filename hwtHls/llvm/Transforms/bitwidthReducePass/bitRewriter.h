#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include "constBitPartsAnalysis.h"
#include <hwtHls/llvm/bitMath.h>

namespace hwtHls {

/**
 * A class which cuts of the reduced bits from the code according to InstructionToVarBitConstraintMap specification.
 *
 * All bits which do have known value on output of the instruction are pruned from the instruction.
 * This means that the type of instruction may have decreased bitwidth. This process is done recursively.
 * For PHINodes we need to first generate replacement, add it to replacementCache and then fill the arguments.
 * This is required because of cycles in dependencies.
 *
 * :note: The reduced instructions are not removed from the code.
 * :note: Individual bits of instructions can be removed no matter the bit position.
 *        The removal is recursive.
 *        if VarBitConstraint::replacements specifies some value which is part of this instr.
 *        it means this instr. will be still required after replacement otherwise the instruction is entirely replaced.
 *
 * :ivar constraints: a dictionary which holds meta-information about which bits are used and what value they may have.
 * :ivar replacementCache: a dictionary mapping original value to its new replacement
 * */
class BitPartsRewriter {
	ConstBitPartsAnalysisContext::InstructionToVarBitConstraintMap &constraints;
	std::map<llvm::Instruction*, llvm::Value*> replacementCache;

	llvm::Value* rewriteKnownBitRangeInfo(llvm::IRBuilder<> *Builder,
			const KnownBitRangeInfo &kbri);
	llvm::Value* rewriteKnownBitRangeInfoVector(llvm::IRBuilder<> *Builder,
			const std::vector<KnownBitRangeInfo> &kbris);
	void rewriteInstructionOperands(llvm::Instruction *I);
	// this functions generates a value of original width with all reduced constant ranges filled in
	// e.g if concat(i8 0, x) was reduced to just x it expands it back to concat(i8 0, x)
	// this is called for operands of instructions which were not modified or replaced to update their value
	llvm::Value* expandConstBits(llvm::IRBuilder<> *b, llvm::Value *origVal,
			llvm::Value *reducedVal, const VarBitConstraint &vbc);

	// rewrite instruction itself, but do not fill the operands, we can not fill operands immediately
	// because this may result in infinite cycle when recursively replacing operands in cyclic SSA.
	llvm::Value* rewritePHINode(llvm::PHINode &I, const VarBitConstraint &vbc);
	// replace this select with an concatenation of bit which are actually used
	llvm::Value* rewriteSelect(llvm::SelectInst &I,
			const VarBitConstraint &vbc);
	llvm::Value* rewriteBinaryOperatorBitwise(llvm::BinaryOperator &I,
			const VarBitConstraint &vbc);
	llvm::Value* rewriteCmpInst(llvm::CmpInst &I, const VarBitConstraint &vbc);

public:
	BitPartsRewriter(
			ConstBitPartsAnalysisContext::InstructionToVarBitConstraintMap &constraints);
	// add for potential rewrite
	llvm::Value* rewriteIfRequired(llvm::Value *V);
	llvm::Value* rewritePHINodeArgsIfRequired(llvm::PHINode *PHI);
};

// :param vbc: the slice containers from where to iterate bits, low to high
std::vector<KnownBitRangeInfo> iterUsedBitRanges(llvm::IRBuilder<> *Builder,
		const llvm::APInt &useMask, const VarBitConstraint &vbc);
}
