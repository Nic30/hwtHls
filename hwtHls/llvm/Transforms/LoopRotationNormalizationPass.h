#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/IR/PassManager.h>

namespace llvm {
class LPMUpdater;
class DomTreeUpdater;
class MemorySSAUpdater;
class Loop;
}

namespace hwtHls {

/*
 * This pass may undo LoopRotatePass (GCC calls it loop header copying) or apply it to the loop.
 * The unroation is beneficial in cases where we can remove costly instructions (memory in this case)
 * by moving pre-header check back to the loop.
 * The LoopRotatePass pass is explained in llvm. The unroatation is explained on following examples:
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
 *
 *  Similar passes in other projects:
 *   * unrotation https://github.com/arcana-lab/noelle/blob/master/src/core/loop_whilifier/src/LoopWhilify.cpp
 * */
class LoopRotationNormalizationPass: public llvm::PassInfoMixin<LoopRotationNormalizationPass> {
public:
	LoopRotationNormalizationPass() :
			dbgCntr(0) {
	}
	llvm::PreservedAnalyses run(llvm::Loop &L, llvm::LoopAnalysisManager &AM,
			llvm::LoopStandardAnalysisResults &AR, llvm::LPMUpdater &U);
	static bool isRequired() {
		return false;
	}
protected:
	size_t dbgCntr;
	bool processLoop(llvm::Loop &L, llvm::LoopStandardAnalysisResults &AR,
			llvm::DomTreeUpdater &DTU, llvm::MemorySSAUpdater *MSSAU,
			llvm::LPMUpdater &LPMU);
};

}
