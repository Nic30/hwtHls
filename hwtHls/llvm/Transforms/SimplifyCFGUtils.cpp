#include <hwtHls/llvm/Transforms/SimplifyCFGUtils.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/Intrinsics.h>
#include <llvm/Analysis/ValueTracking.h>


using namespace llvm;
namespace hwtHls {

unsigned skippedInstrFlags(Instruction *I) {
  unsigned Flags = 0;
  if (I->mayReadFromMemory())
    Flags |= SkipReadMem;
  // We can't arbitrarily move around allocas, e.g. moving allocas (especially
  // inalloca) across stacksave/stackrestore boundaries.
  if (I->mayHaveSideEffects() || isa<AllocaInst>(I))
    Flags |= SkipSideEffect;
  if (!isGuaranteedToTransferExecutionToSuccessor(I))
    Flags |= SkipImplicitControlFlow;
  return Flags;
}


// Returns true if it is safe to reorder an instruction across preceding
// instructions in a basic block.
bool isSafeToHoistInstr(Instruction *I, unsigned Flags) {
  // Don't reorder a store over a load.
  if ((Flags & SkipReadMem) && I->mayWriteToMemory())
    return false;

  // If we have seen an instruction with side effects, it's unsafe to reorder an
  // instruction which reads memory or itself has side effects.
  if ((Flags & SkipSideEffect) &&
      (I->mayReadFromMemory() || I->mayHaveSideEffects()))
    return false;

  // Reordering across an instruction which does not necessarily transfer
  // control to the next instruction is speculation.
  if ((Flags & SkipImplicitControlFlow) && !isSafeToSpeculativelyExecute(I))
    return false;

  // Hoisting of llvm.deoptimize is only legal together with the next return
  // instruction, which this pass is not always able to do.
  if (auto *CB = dyn_cast<CallBase>(I))
    if (CB->getIntrinsicID() == Intrinsic::experimental_deoptimize)
      return false;

  // It's also unsafe/illegal to hoist an instruction above its instruction
  // operands
  BasicBlock *BB = I->getParent();
  for (Value *Op : I->operands()) {
    if (auto *J = dyn_cast<Instruction>(Op))
      if (J->getParent() == BB)
        return false;
  }

  return true;
}


}
