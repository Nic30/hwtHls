#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 * A pass which performs a task similar to a logic minimization.
 * This pass builds an information which bit ranges do have some known value and then cuts of these
 * ranges from original values if it leads to minimization of bitwidth of some operation.
 * (This pass can reduce any bit from value, not just prefix or suffix.)
 *
 * Similar to:
 *   * llvm::BDCEPass
 *     - works only on shifts and extensions
 *   * llvm::KnownBits
 *     - only the structure to discover known 0 or 1 in bit vectors
 *   * llvm::ValueTracking
 *     - only a set of functions to analyze specific patterns
 *   * A generic logic minimizer like ABC, Z3 bit-blast
 *     + performs full minimization
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
 * :note: "this" means this implementation in this class
 **/
class BitwidthReductionPass: public llvm::PassInfoMixin<
		BitwidthReductionPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
	static bool isRequired() { return false; }
};

}
