#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  Simplify trivial patterns in CFG
 *  * Remove empty basic block if:
 *    * has single successor and predecessor or no phis
 *    * and may be replaced by predecessor in successor PHIs
 *       * only if pruneSinglePredSingleSucBlocks=true
 *       * breaks loop canonical form which many passes depends on
 *  * Remove one operand PHIs and PHIs with all same values
 *    * breaks loop canonical form for exit blocks
 *  * Simplifies conditional jumps jumping to the same target for every value of condition
 *
 *  :note: Primary purpose of this pass is to make code more readable for debugging. For real
 *  CFG simplification there is SimplifyCFG2Pass, SimplifyCFGPass.
 */
class TrivialSimplifyCFGPass: public llvm::PassInfoMixin<
TrivialSimplifyCFGPass> {
	bool pruneSinglePredSingleSucBlocks;
public:
	TrivialSimplifyCFGPass(bool pruneSinglePredSingleSucBlocks);
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
