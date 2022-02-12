#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 * A pass which performs a task similar to a logic minimization.
 * This it builds an information which bit ranges do have some known value and then cuts of these
 * ranges from original values if it leads to minimization of bitwidth of some operation.
 *
 * Similar to:
 *   * A generic logic minimizer like ABC
 *     + performs complete minimization
 *     - computationally complex, destroys the information about used operands and thus prevents other optimization
 *   * ctoverilog xVerilog::ReduceWordWidthPass
 *     - this can in addition reduce bitwise ops and reduce bits from anywhere not just start
 *     + can reduce additions/multiplications with extension
 *   * legup::MinimizeBitwidth
 *     - this supports values >128b
 *     - this optimization reduces same values not just same constants
 *     - this works just with 2 passes, all opt. are resolved before actual SSA modification (legup opt. does it iteratively)
 *   * Shang BitLevelOpt
 *     - works only on machine level
 *     - based only or rewrite of a single instruction
 *   * VitisHLS - modified llvm::InstCombine
 *     - custom version of llvm 6.0.1
 *     - worklist driven = reduced search distance
 **/
class ConstantBitPropagationPass: public llvm::PassInfoMixin<
		ConstantBitPropagationPass> {

public:
	static llvm::StringRef name() {
		return "ConstantBitPropagationPass";
	}

	explicit ConstantBitPropagationPass() {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
