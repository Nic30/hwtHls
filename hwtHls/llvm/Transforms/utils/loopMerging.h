#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>

namespace hwtHls {

void mergeNestedLoops(llvm::LoopInfo &LI, llvm::ScalarEvolution *SE,
		llvm::LPMUpdater &LPMU, llvm::Loop *L1, llvm::Loop *L0);

}
