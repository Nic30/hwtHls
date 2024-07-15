#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  For loop header predecessor check all PHIs if incoming value of any no-poison, no-undef value lives to next iteration
 *  or has any use with any effect in this loop iteration.
 *
 *  :note: llvm::PruneLoopPhiDeadIncommingValuesPass is not loop pass because it works with non-normalized loops.
 *
 *  This is useful when there is code like:
 *
 *  .. code-block::cpp
 *    for (;;) {
 *      if (c) {
 *        x++;
 *        if (y > 10) {
 *          x = 0;
 *          c = !c;
 *        }
 *      } else {
 *        y++;
 *        if (y > 10) {
 *          y = 0;
 *          c = !c;
 *        }
 *      }
 *    }
 *
 * In this case value of y can be poison/undef during iteration of x, and same applies for x.
 * However by default it would be resolved that the value should stay 0.
 * Removing 0 may allow for more optimization opportunities and reduces register pressure.
 *
 */
class PruneLoopPhiDeadIncomingValuesPass: public llvm::PassInfoMixin<
		PruneLoopPhiDeadIncomingValuesPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
