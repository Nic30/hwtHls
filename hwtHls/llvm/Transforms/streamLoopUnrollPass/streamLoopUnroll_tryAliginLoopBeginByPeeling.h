#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>
#include <llvm/Analysis/SimplifyQuery.h>
#include <llvm/ADT/SetVector.h>

#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

namespace hwtHls {

llvm::LoopUnrollResult tryAliginLoopBeginByPeeling(llvm::DominatorTree &DT,
		llvm::LoopInfo *LI, llvm::ScalarEvolution &SE,
		const llvm::TargetLibraryInfo &TLI,
		const llvm::TargetTransformInfo &TTI, llvm::AssumptionCache &AC,
		llvm::OptimizationRemarkEmitter &ORE, bool PreserveLCSSA,
		StreamChannelProps &streamProps, llvm::Function &F, llvm::Loop *L,
		const llvm::SetVector<size_t> &entryOffsets,
		size_t minNumberOfBitsProcessedPerIteration,
		const llvm::SetVector<size_t> &_minNumberOfBitsProcessedPerIteration);
}
