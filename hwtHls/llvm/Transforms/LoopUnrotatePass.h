#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/IR/PassManager.h>

namespace llvm {
class LPMUpdater;
class Loop;
}

namespace hwtHls {

/*
 * Undo LoopRotatePass (GCC calls it loop header copying)
 * This is beneficial in the cases where we can remove number of load instructions
 * by moving pre-header check back to loop.
 *
 * From:
 * .. code-block:: c
 *   uint8_t v = 0;
 *   if (*cPtr) {
 *     do {
 *       v++;
 *     } while (*cPtr);
 *   }
 * to:
 * .. code-block:: c
 *   uint8_t v = 0;
 *   while (*cPtr) {
 *      v++;
 *   }
 *
 * Same as previous examples just in llvm IR
 * .. code-block:: llvm
 *     ...
 *    guard:
 *      %c0 = load i1 ptr %cPtr
 *      br i1 %c0, label %preheader, %guardExit
 *    preheader:
 *      br label %loopHeader
 *    loopHeader:
 *      %v0 = phi i8 [%v1, %loopHeader], [0, %preheader]
 *      %v1 = add i8 %v0, 1
 *      %c1 = load i1 ptr %cPtr
 *      br i1 %c1, label %loopHeader, %loopExit
 *    loopExit:
 *      %v.lcssa = phi i8 [%v1, %loopHeader]
 *      br label %guardExit
 *    guardExit:
 *      %v2 = phi i8 [0, %guard], [%v.lcssa, %loopExit]
 *      ...
 *
 *
 * .. code-block:: llvm
 *   guard:
 *     %v2 = phi i8 [%v1, %loopHeader], [0, %guardPred]
 *     %v0 = phi i8
 *     %c0 = load i1 ptr %cPtr
 *     br i1 %c0, label %preheader, %guardExit
 *   preheader:
 *     br label %loopHeader
 *   loopHeader:
 *     %v1 = add i8 %v2, 1
 *     br label %guard
 *   guardExit:
 *     ...
 *
 * :attention: if there are multiple variables modified in the loop and some of them
 *    are not used behind the loop the loopHeader block will contain additional PHIs which must be moved to guard block
 * */
class LoopUnrotatePass: public llvm::PassInfoMixin<LoopUnrotatePass> {
public:
	llvm::PreservedAnalyses run(llvm::Loop &L, llvm::LoopAnalysisManager &AM,
			llvm::LoopStandardAnalysisResults &AR, llvm::LPMUpdater &U);
};

}
