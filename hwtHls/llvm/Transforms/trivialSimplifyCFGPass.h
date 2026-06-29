#pragma once

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/DomTreeUpdater.h>

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
 *  CFG simplification there is HwtHlsSimplifyCFGPass, SimplifyCFGPass.
 */
class TrivialSimplifyCFGPass: public llvm::PassInfoMixin<
TrivialSimplifyCFGPass> {
	bool pruneSinglePredSingleSucBlocks;
	bool allowPhiNewIncommingValues; // allow to add new incoming values for PHIs
		// this option is dangerous in general case because it may result in loop header blocks being
	    // merged with to block with PHIs with many incoming values which is then hard to optimize.
	void onChangeCallback(const std::string & ruleName, llvm::Function & F);
	bool tryRemoveSingleSuccessorBlockIfNotLatch(llvm::DomTreeUpdater &DTU,
			const bool allowPhiNewIncommingValues, llvm::BasicBlock *BB,
			llvm::SmallSetVector<llvm::WeakVH, 16> &WorkList);
public:
	using IrChangeCallbackFn = std::function<void(const std::string & ruleName, const llvm::Function & F)>;
	IrChangeCallbackFn* _dbgIrCfgSimplifyChangeCallbackFn = nullptr;
	TrivialSimplifyCFGPass(bool pruneSinglePredSingleSucBlocks, bool allowPhiNewIncommingValues, IrChangeCallbackFn* dbgIrCfgSimplifyChangeCallbackFn);
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
