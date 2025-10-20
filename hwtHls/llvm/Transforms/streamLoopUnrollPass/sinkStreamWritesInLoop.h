#pragma once

#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/TargetLibraryInfo.h>

namespace hwtHls {

void sinkStreamWritesInLoop(llvm::Loop &L, llvm::ScalarEvolution &SE,
		llvm::DominatorTree &DT, llvm::LoopInfo &LI, llvm::AssumptionCache &AC,
		const llvm::TargetLibraryInfo &TLI,
		const llvm::TargetTransformInfo &TTI, bool PreserveLCSSA);

}
