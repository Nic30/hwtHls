#pragma once

#include <llvm/Transforms/Utils/LoopPeel.h>

namespace hwtHls {

// :note: same as llvm::peelLoop but it also exports peeled headers and disabled simplifyLoop
//     at the end.
//     Original intent when copying was to add additional predecessors to peeled loop headers
//     and simplifyLoop is disabled because it may modify header phis.
// :note: this implies that you should call simplifyLoop as in original after finishing updates.
bool hwtHls_peelLoop(llvm::Loop *L, unsigned PeelCount, llvm::LoopInfo *LI,
		llvm::ScalarEvolution *SE, llvm::DominatorTree &DT,
		llvm::AssumptionCache *AC, bool PreserveLCSSA,
		llvm::ValueToValueMapTy &LVMap,
		llvm::SmallVector<llvm::BasicBlock*> &peeledHeaders);
}
