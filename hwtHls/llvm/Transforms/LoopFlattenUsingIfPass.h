#pragma once

#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/IR/PassManager.h>

namespace llvm {
class LPMUpdater;
class Loop;
}

namespace hwtHls {

/**
 *  Merge child loop into parent, use flag to switch between body and condition of parent or child.
 *  :attention: FoldCondBranchOnValueKnownInPredecessorImpl from SimplifyCFG reverts transformed code back to original
 *    whole point of this transformation is to allow code hoisting and sinking.
 *    This is useful in cases where most of the code can be sinked or hoisted.
 *    If this is the case the SimplifyCFG will then just slice off and remove empty parent loop.
 *    This can be done by running SimplifyCFG and alike with HoistCheapInsts=true, HoistCommonInsts=true
 *
 *  .. code-block::cpp
 *
 *       // :note: both loops can be in rotated do-while format or in while format
 *       //        do-while is better as the condition is at the end and we can evaluate jump immediately
 *       //        after loop body and there is no extra loop iteration needed to evaluate it
 *       //        and there is no potential code duplication for the check
 *       while (parentCond()) {
 *           // :note: case where fn0 and fn1 is not present is called “perfect” nested loop
 *           // https://www.cs.cornell.edu/courses/cs6120/2020fa/blog/loop-flatten/
 *           fn0();
 *           for (childInit(); childCond(); childStep())
 *               childBody();
 *           fn1();
 *       }
 *
 *
 *       bool isInChildLoop = false;
 *       while (isInChildLoop || parentCond()) {
 *           // all child lineins are set to undef on enter or to value from previous iteration on reenter
 *           if (!isInChildLoop) {
 *               fn0();
 *               childInit();
 *               isInChildLoop = true;
 *           }
 *           bool childContinue = childCond();
 *           if (childContinue) {
 *               childBody(&childContinue); // continue and breaks update childContinue flag and always jumps there or behind childStep (if it is break)
 *               childStep();
 *           }
 *           if (canDuplcate(childCond)) {
 *               if (childContinue)
 *                   childContinue &= childCond()
 *               // :note: now we childCond() is using values updated by childStep()
 *           } // else this requires 1 iteration more to set isInChildLoop=false after nested loop ends
 *
 *           if (!childContinue) {
 *               isInChildLoop = false;
 *               fn1();
 *           }
 *       }
 *
 *  :note: works for all types of loops including rotated loops (do-while)
 *
 *  .. figure:: ./_static/LoopFlattenUsingIfPass.png
 */
class LoopFlattenUsingIfPass: public llvm::PassInfoMixin<LoopFlattenUsingIfPass> {
public:
	static const std::string METADATANAME_MODE;
	enum Mode {
		CHILD_LOOP_ENTRY_IN_SAME_ITERATION,
		CHILD_LOOP_ENTRY_IN_NEXT_ITERATION,
	};
	static Mode modeStringToMode(const llvm::StringRef mode);
	llvm::PreservedAnalyses run(llvm::Loop &L, llvm::LoopAnalysisManager &AM,
				llvm::LoopStandardAnalysisResults &AR, llvm::LPMUpdater &U);
};

}
