#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>
#include <llvm/Analysis/SimplifyQuery.h>

namespace hwtHls {

struct StreamLoopUnrollArgs {
	llvm::Argument &ioArg;
	bool alignLoopBodyBeginByPrequelExtract;

	static std::optional<StreamLoopUnrollArgs> getFromLoop(
			const llvm::Loop *TheLoop);
};

llvm::LoopUnrollResult tryToUnrollStreamLoop(llvm::Function &F, llvm::Loop *L,
		llvm::SimplifyQuery &SQ, llvm::DominatorTree &DT, llvm::LoopInfo *LI,
		llvm::ScalarEvolution &SE, const llvm::TargetLibraryInfo &TLI,
		const llvm::TargetTransformInfo &TTI, llvm::AssumptionCache &AC,
		llvm::OptimizationRemarkEmitter &ORE, llvm::BlockFrequencyInfo *BFI,
		llvm::ProfileSummaryInfo *PSI, bool PreserveLCSSA, int OptLevel,
		bool OnlyWhenForced, bool ForgetAllSCEV,
		std::optional<unsigned> ProvidedCount,
		std::optional<unsigned> ProvidedThreshold,
		std::optional<bool> ProvidedAllowPartial,
		std::optional<bool> ProvidedRuntime,
		std::optional<bool> ProvidedUpperBound,
		std::optional<bool> ProvidedAllowPeeling,
		std::optional<bool> ProvidedAllowProfileBasedPeeling,
		std::optional<unsigned> ProvidedFullUnrollMaxCount);
}
