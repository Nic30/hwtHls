#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnrollPass.h>

#include <llvm/ADT/PriorityWorklist.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/Analysis/ProfileSummaryInfo.h>
#include <llvm/Analysis/TargetLibraryInfo.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Scalar/LoopUnrollPass.h>

#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnroll_tryToUnrollStreamLoop.h>


#define DEBUG_TYPE "StreamLoopUnroll"
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(X) { X; }

using namespace llvm;

namespace hwtHls {


const char *const LLVMLoopUnrollFollowupAll =
		"hwthls.loop.streamunroll.followup_all";
const char *const LLVMLoopUnrollFollowupUnrolled =
		"hwthls.loop.streamunroll.followup_unrolled";
const char *const LLVMLoopUnrollFollowupRemainder =
		"hwthls.loop.streamunroll.followup_remainder";


const std::string StreamLoopUnrollPass::METADATA_NAME =
		"hwthls.loop.streamunroll.io";

llvm::PreservedAnalyses StreamLoopUnrollPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	LoopUnrollOptions UnrollOpts;
	// same as LoopUnrollPass::run just with different main function for loop transformation (tryToUnrollStreamLoop)
	auto &LI = AM.getResult<LoopAnalysis>(F);
	// There are no loops in the function. Return before computing other expensive
	// analyses.
	if (LI.empty())
		return PreservedAnalyses::all();
	auto &SE = AM.getResult<ScalarEvolutionAnalysis>(F);
	auto &TLI = AM.getResult<TargetLibraryAnalysis>(F);
	auto &TTI = AM.getResult<TargetIRAnalysis>(F);
	auto &DT = AM.getResult<DominatorTreeAnalysis>(F);
	auto &AC = AM.getResult<AssumptionAnalysis>(F);
	auto &ORE = AM.getResult<OptimizationRemarkEmitterAnalysis>(F);

	LoopAnalysisManager *LAM = nullptr;
	if (auto *LAMProxy = AM.getCachedResult<LoopAnalysisManagerFunctionProxy>(
			F))
		LAM = &LAMProxy->getManager();

	auto &MAMProxy = AM.getResult<ModuleAnalysisManagerFunctionProxy>(F);
	ProfileSummaryInfo *PSI = MAMProxy.getCachedResult<ProfileSummaryAnalysis>(
			*F.getParent());
	auto *BFI =
			(PSI && PSI->hasProfileSummary()) ?
					&AM.getResult<BlockFrequencyAnalysis>(F) : nullptr;

	auto SQ = getBestSimplifyQuery(AM, F);
	bool Changed = false;

	// The unroller requires loops to be in simplified form, and also needs LCSSA.
	// Since simplification may add new inner loops, it has to run before the
	// legality and profitability checks. This means running the loop unroller
	// will simplify all loops, regardless of whether anything end up being
	// unrolled.
	for (const auto &L : LI) {
		Changed |= simplifyLoop(L, &DT, &LI, &SE, &AC, nullptr,
				false /* PreserveLCSSA */);
		Changed |= formLCSSARecursively(*L, DT, &LI, &SE);
	}

	// Add the loop nests in the reverse order of LoopInfo. See method
	// declaration.
	SmallPriorityWorklist<Loop*, 4> Worklist;
	appendLoopsToWorklist(LI, Worklist);

	while (!Worklist.empty()) {
		// Because the LoopInfo stores the loops in RPO, we walk the worklist
		// from back to front so that we work forward across the CFG, which
		// for unrolling is only needed to get optimization remarks emitted in
		// a forward order.
		Loop &L = *Worklist.pop_back_val();
#ifndef NDEBUG
		Loop *ParentL = L.getParentLoop();
#endif

		// Check if the profile summary indicates that the profiled application
		// has a huge working set size, in which case we disable peeling to avoid
		// bloating it further.
		std::optional<bool> LocalAllowPeeling = UnrollOpts.AllowPeeling;
		//if (PSI && PSI->hasHugeWorkingSetSize())
		//	LocalAllowPeeling = false;
		std::string LoopName = std::string(L.getName());
		// The API here is quite complex to call and we allow to select some
		// flavors of unrolling during construction time (by setting UnrollOpts).
		LoopUnrollResult Result = tryToUnrollStreamLoop(F, &L, SQ, DT, &LI, SE,
				TLI, TTI, AC, ORE, BFI, PSI,
				/*PreserveLCSSA*/true, UnrollOpts.OptLevel,
				UnrollOpts.OnlyWhenForced, UnrollOpts.ForgetSCEV, /*Count*/
				std::nullopt,
				/*Threshold*/std::nullopt, UnrollOpts.AllowPartial,
				UnrollOpts.AllowRuntime, UnrollOpts.AllowUpperBound,
				LocalAllowPeeling, UnrollOpts.AllowProfileBasedPeeling,
				UnrollOpts.FullUnrollMaxCount);
		Changed |= Result != LoopUnrollResult::Unmodified;

		// The parent must not be damaged by unrolling!
#ifndef NDEBUG
		if (Result != LoopUnrollResult::Unmodified && ParentL)
			ParentL->verifyLoop();
#endif

		// Clear any cached analysis results for L if we removed it completely.
		if (LAM && Result == LoopUnrollResult::FullyUnrolled)
			LAM->clear(L, LoopName);
	}

	if (!Changed)
		return PreservedAnalyses::all();
	return getLoopPassPreservedAnalyses();
}

}
