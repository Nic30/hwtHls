#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnrollPass.h>
#include <llvm/ADT/PriorityWorklist.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/Analysis/ProfileSummaryInfo.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Transforms/Utils/LoopPeel.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Scalar/LoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopInfo.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/bitMath.h>


#define DEBUG_TYPE "StreamLoopUnroll"

using namespace llvm;

namespace hwtHls {

/*
 * Discover how many bits of stream are processed by a single iteration of the loop to resolve
 * */
void collectMinimalStreamProccessedBitWidthForLoop(Loop *L,
		StreamChannelProps streamProps, llvm::SetVector<size_t> &resSizes,
		llvm::SetVector<llvm::CallInst*> &resEntryStreamIos,
		size_t currentWidth, BasicBlock &B, BasicBlock::iterator curI) {
	assert(&B != nullptr);
	assert(
			L->isInnermost()
					&& "temporary assert we can allow subloops which do not process variable number of stream bits");
	auto I = curI;
	if (I == B.end())
		return;

	for (; I != B.end(); ++I) {
		auto CI = dyn_cast<CallInst>(I);
		if (CI && streamProps.ios.count(&*CI)) {
			if (IsStreamIoEndOfFrame(CI) || IsStreamIoStartOfFrame(CI)) {
			} else {
				if (currentWidth == 0)
					resEntryStreamIos.insert(CI);
				currentWidth += streamIoGetOrigChunkBitWidth(CI);
			}
		}
	}
	for (auto suc : llvm::successors(&B)) {
		if (L->getHeader() != suc && L->contains(suc)) {
			collectMinimalStreamProccessedBitWidthForLoop(L, streamProps,
					resSizes, resEntryStreamIos, currentWidth, *suc,
					suc->begin());
		} else {
			resSizes.insert(currentWidth);
		}
	}
}

// based on llvm LoopUnrollPass.cpp tryToUnrollLoop()
static LoopUnrollResult tryToUnrollStreamLoop(llvm::Function &F, Loop *L,
		DominatorTree &DT, LoopInfo *LI, ScalarEvolution &SE,
		const TargetTransformInfo &TTI, AssumptionCache &AC,
		OptimizationRemarkEmitter &ORE, BlockFrequencyInfo *BFI,
		ProfileSummaryInfo *PSI, bool PreserveLCSSA, int OptLevel,
		bool OnlyWhenForced, bool ForgetAllSCEV,
		std::optional<unsigned> ProvidedCount,
		std::optional<unsigned> ProvidedThreshold,
		std::optional<bool> ProvidedAllowPartial,
		std::optional<bool> ProvidedRuntime,
		std::optional<bool> ProvidedUpperBound,
		std::optional<bool> ProvidedAllowPeeling,
		std::optional<bool> ProvidedAllowProfileBasedPeeling,
		std::optional<unsigned> ProvidedFullUnrollMaxCount) {
	LLVM_DEBUG(
			dbgs() << "Stream Loop Unroll: F["
					<< L->getHeader()->getParent()->getName() << "] Loop %"
					<< L->getHeader()->getName() << "\n");
	auto streamArgI = getOptionalIntHwtHlsLoopAttribute(L,
			"hwthls.loop.streamunroll.io");
	if (!streamArgI.has_value()) {
		// loop does not have Attribute to enable this transformation
		return LoopUnrollResult::Unmodified;
	}
	if (!L->isLoopSimplifyForm()) {
		LLVM_DEBUG(
				dbgs()
						<< "  Not unrolling loop which is not in loop-simplify form.\n");
		return LoopUnrollResult::Unmodified;
	}

	Argument &IoArg = *F.getArg(streamArgI.value());

	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	StreamChannelProps streamProps = getStreamIoProps(F, GeneratedAllocas,
			&IoArg).at(0);
	assert(
			GeneratedAllocas.size() == 0
					&& "This should not be used because we should only use positions in stream in this alg.");

	llvm::SetVector<size_t> _minNumberOfBitsProcessedPerIteration;
	llvm::SetVector<llvm::CallInst*> entryStreamIos;
	collectMinimalStreamProccessedBitWidthForLoop(L, streamProps,
			_minNumberOfBitsProcessedPerIteration, entryStreamIos, 0,
			*L->getHeader(), L->getHeader()->begin());
	size_t minNumberOfBitsProcessedPerIteration = 0;
	for (auto bw : _minNumberOfBitsProcessedPerIteration) {
		if (bw > 0
				&& (minNumberOfBitsProcessedPerIteration == 0
						|| bw < minNumberOfBitsProcessedPerIteration))
			minNumberOfBitsProcessedPerIteration = bw;
	}
	if (minNumberOfBitsProcessedPerIteration == 0) {
		throw std::runtime_error(
				"StreamLoopUnrollPass: minimal number of stream bits processed per iteration must be >0");
	}
	StreamIoDetector cfg(streamProps.dataWidth,
			reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(streamProps.ios));
	cfg.detectIoAccessGraphs(F.getEntryBlock());
	cfg.resolvePossibleOffset();
	if (entryStreamIos.size() != 1)
		throw std::runtime_error(
				"NotImplemented: StreamLoopUnrollPass multiple independent entry points to stream processing in loop body.");

	size_t minEntryOffset = streamProps.dataWidth;
	for (auto *entryStreamI : entryStreamIos) {
		// we are looking at predecessors because we want to use offsets possible on entry of the loop
		// without offset variants generated from re-entry
		for (auto *predStreamI : cfg.predecessors[entryStreamI]) {
			bool isReenterInLoop = L->contains(predStreamI);
			if (isReenterInLoop)
				continue;
			auto w = streamIoGetOrigChunkBitWidth(predStreamI);
			for (auto oOff : cfg.inWordOffset[predStreamI]) {
				auto entryOff = (w + oOff) % streamProps.dataWidth;
				if (entryOff == 0)
					continue; // we are not interested in aligned values as they do not pose any problem
				if (entryOff < minEntryOffset)
					minEntryOffset = entryOff;
			}
		}
	}
	if (minEntryOffset == streamProps.dataWidth)
		minEntryOffset = 0;

	errs() << "minNumberOfBitsProcessedPerIteration"
			<< minNumberOfBitsProcessedPerIteration << " minEntryOffset:"
			<< minEntryOffset << "\n";

	// [todo] resolve amount of bits taken/added from/to stream per iteration and from possible offsets of loop header resolve
	// how many times to peel and how many times to unroll to achieve desired throughput
	if (minEntryOffset == 0) {
		// no peeling required
	} else {
		throw std::runtime_error("NotImplemented");
		TargetTransformInfo::PeelingPreferences PP;
		if (PP.PeelCount) {
			//assert(
			//		UP.Count == 1
			//				&& "Cannot perform peel and unroll in the same step");
			LLVM_DEBUG(
					dbgs() << "PEELING loop %" << L->getHeader()->getName()
							<< " with iteration count " << PP.PeelCount << "!\n");
			ORE.emit(
					[&]() {
						return OptimizationRemark(DEBUG_TYPE, "Peeled",
								L->getStartLoc(), L->getHeader())
								<< " peeled loop by "
								<< ore::NV("PeelCount", PP.PeelCount)
								<< " iterations";
					});

			ValueToValueMapTy VMap;
			if (peelLoop(L, PP.PeelCount, LI, &SE, DT, &AC, PreserveLCSSA, VMap)) {
				simplifyLoopAfterUnroll(L, true, LI, &SE, &DT, &AC, &TTI);
				// If the loop was peeled, we already "used up" the profile information
				// we had, so we don't want to unroll or peel again.
				if (PP.PeelProfiledIterations)
					L->setLoopAlreadyUnrolled();
				return LoopUnrollResult::PartiallyUnrolled;
			}
			return LoopUnrollResult::Unmodified;
		}
	}
	UnrollLoopOptions UP;
	UP.Count = div_ceil(streamProps.dataWidth - minEntryOffset, minNumberOfBitsProcessedPerIteration);
	UP.Force = true;
	UP.Runtime = true;
	UP.AllowExpensiveTripCount = true;
	UP.UnrollRemainder = true;
	UP.ForgetAllSCEV = ForgetAllSCEV;


	// Save loop properties before it is transformed.
	MDNode *OrigLoopID = L->getLoopID();

	// Unroll the loop.
	Loop *RemainderLoop = nullptr;
	LoopUnrollResult UnrollResult = UnrollLoop(L,
			{ UP.Count, UP.Force, UP.Runtime, UP.AllowExpensiveTripCount,
					UP.UnrollRemainder, ForgetAllSCEV }, LI, &SE, &DT, &AC,
			&TTI, &ORE, PreserveLCSSA, &RemainderLoop);
	if (UnrollResult == LoopUnrollResult::Unmodified)
		return LoopUnrollResult::Unmodified;

	if (RemainderLoop) {
		std::optional<MDNode*> RemainderLoopID = makeFollowupLoopID(OrigLoopID,
				{ LLVMLoopUnrollFollowupAll, LLVMLoopUnrollFollowupRemainder });
		if (RemainderLoopID)
			RemainderLoop->setLoopID(*RemainderLoopID);
	}

	if (UnrollResult != LoopUnrollResult::FullyUnrolled) {
		std::optional<MDNode*> NewLoopID = makeFollowupLoopID(OrigLoopID, {
				LLVMLoopUnrollFollowupAll, LLVMLoopUnrollFollowupUnrolled });
		if (NewLoopID) {
			L->setLoopID(*NewLoopID);

			// Do not setLoopAlreadyUnrolled if loop attributes have been specified
			// explicitly.
			return UnrollResult;
		}
	}

	// If loop has an unroll count pragma or unrolled by explicitly set count
	// mark loop as unrolled to prevent unrolling beyond that requested.
	// [todo]

	return UnrollResult;
}

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
		LoopUnrollResult Result = tryToUnrollStreamLoop(F, &L, DT, &LI, SE, TTI,
				AC, ORE, BFI, PSI,
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
