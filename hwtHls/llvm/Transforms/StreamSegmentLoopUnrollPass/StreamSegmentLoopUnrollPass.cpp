#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/StreamSegmentLoopUnrollPass.h>

#include <llvm/ADT/PriorityWorklist.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/ScalarEvolution.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/OptimizationRemarkEmitter.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/Analysis/ProfileSummaryInfo.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Transforms/Utils/LoopUtils.h>
#include <llvm/Transforms/Utils/UnrollLoop.h>
#include <llvm/Transforms/Utils/LoopSimplify.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/PromoteMemToReg.h>
#include <llvm/Transforms/Scalar/LoopUnrollPass.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/sinkStreamWritesInLoop.h>
#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/liveness.h>
#include <hwtHls/llvm/Analysis/mergeSetsBasedLivenessAnalysis/mergeSets.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/splitBBsOnIOAccess.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/constructCodeLanesForSegments.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/chainedRerouteLaneCfg.h>
#include <hwtHls/llvm/Transforms/StreamSegmentLoopUnrollPass/demoteAllLiveVarsOnLaneCrossingToTmpAlloca.h>

// #include <llvm/IR/Verifier.h>
// #include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

#define DEBUG_TYPE "StreamSegmentLoopUnroll"
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(X) { X; }

using namespace llvm;

namespace hwtHls {

// based on llvm LoopUnrollPass.cpp tryToUnrollLoop(), StreamLoopUnrollPass
// :attention: invalidates LI, SE
static LoopUnrollResult tryToUnrollStreamSegmentLoop(llvm::Function &F, Loop &L,
		DominatorTree &DT, LoopInfo &LI, ScalarEvolution &SE,
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
		std::optional<unsigned> ProvidedFullUnrollMaxCount,
		std::vector<AllocaInst*> &tmpAllocas,
		llvm::FunctionAnalysisManager &AMForDebug) {
	auto streamArgI = getOptionalIntHwtHlsLoopAttribute(&L,
			StreamSegmentLoopUnrollPass::METADATA_NAME_io);
	auto allowSoFOnlyFor = getOptionalIntVecHwtHlsLoopAttribute(&L, StreamSegmentLoopUnrollPass::METADATA_NAME_allowSoFOnlyFor);
	if (!streamArgI.has_value()) {
		LLVM_DEBUG(
				dbgs()
						<< "  Loop does not have hwthls.loop.streamloopunroll.io Attribute to enable this transformation.\n");
		// loop does not have Attribute to enable this transformation
		return LoopUnrollResult::Unmodified;
	}
	LLVM_DEBUG(
			dbgs() << "Stream Segment Loop Unroll: F["
					<< L.getHeader()->getParent()->getName() << "] Loop %"
					<< L.getHeader()->getName() << "\n");
	if (!L.isLoopSimplifyForm()) {
		LLVM_DEBUG(
				dbgs()
						<< "  Not unrolling loop which is not in loop-simplify form.\n");
		return LoopUnrollResult::Unmodified;
	}

	Argument &IoArg = *F.getArg(streamArgI.value());
	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	// get stream props for specified IoArg
	StreamChannelProps streamProps = findStreamIoPropsInMetadata(F, &IoArg,
			GeneratedAllocas);
	assert(GeneratedAllocas.empty());
	if (streamProps.segmentCnt == 1)
		return LoopUnrollResult::Unmodified; // no unrolling required

	std::string errTmp =
			"StreamSegmentLoopUnrollPass requires all accesses to IO to be present inside of the loop, users outside of loop:\n";
	llvm::raw_string_ostream errSS(errTmp);
	bool hasUserOutsideOfLoop= false;
	for (auto U: IoArg.users()) {
		if (auto UI = dyn_cast<Instruction>(U)) {
			if (!L.contains(UI)) {
				errSS << *UI << "\n";
				hasUserOutsideOfLoop = true;
			}
		}
	}
	if (hasUserOutsideOfLoop)
		throw std::runtime_error(errSS.str());
	SE.forgetLoop(&L);
	{
		// :note: the PHIs are known to be only in header, other split point do not have PHIs
		//  because the split was just created using SplitBlock on the place where Load/Store inst
		//  was
		demoteBlockPHIsToAlloca(tmpAllocas, *L.getHeader());
		SmallVector<BasicBlock *> ExitBlocks;
		L.getExitBlocks(ExitBlocks);
		for (auto E: ExitBlocks) {
			demoteBlockPHIsToAlloca(tmpAllocas, *E);
		}
	}
	// Save loop properties before it is transformed.
	MDNode *OrigLoopID = L.getLoopID();
	//MDNode *OrigHwtHlsLoopID = Loop_getHwtHlsLoopID(*L);
	L.setLoopID(nullptr); // temporary delete before CFG modifications
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
	bool ioIsInput;
	SmallVector<BasicBlock*> BBs;
	SmallVector<Instruction*> IoInstructions;
	splitBBsOnIOAccess(DTU, LI, L, IoArg, ioIsInput, BBs, IoInstructions);
	DTU.flush();
#ifndef NDEBUG
	LI.verify(DT);
#endif
	/// Get computed DJ-graph of the control flow graph.
	DJGraph djGraph = computeDJGraph(F, DT);
	MergeSets mergeSets = completeTopDownMergeSetComputation(djGraph, F, DT);
	auto allLiveins = allLiveInUsingMergeSet(F.getEntryBlock(), DT, mergeSets);
	IRBuilder<> Builder(F.getContext());
	demoteAllLiveVarsOnLaneCrossingToTmpAlloca(Builder, F, ioIsInput,
			allLiveins, BBs, IoInstructions, tmpAllocas);
#ifndef NDEBUG
	LI.verify(DT);
#endif

	// writeCFGToDotFile(F, "tmp/StreamSegmentLoopUnrollPass.1.normalized.dot", AMForDebug,
	// 		false, true);

 	//assert(DT.verify());
	// errs() << "\n";
 	// for (auto &L : LI) {
 	// 	L->dumpVerbose();
 	// 	errs() << "\n";
 	// }
 	//LI.verify(DT);

	SmallVector<SmallVector<BasicBlock*>> loopBodyCopies;
	// :note: unique_ptr is used because ValueToValueMapTy is non-copyiable, non-movable
	auto valueMaps = std::unique_ptr<ValueToValueMapTy[]>(
			new ValueToValueMapTy[streamProps.segmentCnt]); // last value map is has key=value and is for original code

	copyCodeForLanes(streamProps, LI, L, DTU, BBs, loopBodyCopies, valueMaps, F);
	DTU.flush();
	//assert(DTU.getDomTree().verify());

	//writeCFGToDotFile(F, "tmp/StreamSegmentLoopUnrollPass.1.dot", AMForDebug,
	//		false, true);
	std::map<BasicBlock*, unsigned> BBToLaneIndex;
	std::map<BasicBlock*, unsigned> BBToIndexInloopBodyCopies;
	buildBlockIndexMaps(loopBodyCopies, BBToIndexInloopBodyCopies,
			BBToLaneIndex);

	// copy the body block segment-times
	// * entry block of non-(last for input, first for output) lane will have no predecessor
	//   * :note: for input the section starts after LoadInst and thus the lane for last segment will be connected
	//            before first lane
	// * exit block of non-last lane will have no successors
	//   * :note: jumps between lanes are not constructed yet and this is original exit/backedge of the loop

	// convert registers defined inside of the loop to tmp variable using AllocaInst if its
	// liveness is crossing the newly created edges or if they are primary inputs/outputs
	// of the section which will be unrolled
	// :note: Tmp variables are used because llvm::RemapInstruction would not be sufficient
	//        because block in section of next lane does not need to be dominated by a single predecessor
	//        in previous lane, thus some extra PHIs are required if this is the case
	//        The llvm CodeExtractor approach (liveins/liveouts of extracted region)
	//        is not applicable there because it works only for regions dominated by a single block
	//        there new section are generated from code between LoadInst/Store inst which may not
	//        dominate each other and blocks from different lanes will be connected together.
	//        Resulting in a situation where variable which was originally provided from this lane
	//        may be provided from different one because there was some additional Load/Store on the path.
	//        Which is now processed by a different lane.

	// if this IO is input extend reads in the first lane to bus word width and in all other
	// use this value instead
	// if this IO is output, extend writes in last lane to bus word width and all others
	// will stack data to tmp variable instead

	// reroute edges which were generated after original LoadInst/StoreInst of this IO
	// * the edge always leads to next lane instead of continuing in current one
	// * the edges from last lane will lead to first lane
	// * backedges of on-last lane will be rerouted to first lane head bb
	rerouteLaneCfgAndSegmentValue(Builder, F, DTU, LI, streamProps, tmpAllocas,
			IoInstructions, valueMaps, BBToLaneIndex, BBToIndexInloopBodyCopies,
			loopBodyCopies, allowSoFOnlyFor);
	//F.dump();
	//writeCFGToDotFile(F, "tmp/StreamSegmentLoopUnrollPass.2.dot", AMForDebug,
	//		false, true);

	// this generates code for lanes in loop, but it is expected that the top loop is infinite
	// loop
	L.setLoopID(OrigLoopID); // return id back after cfg modifications
	DTU.flush();

	//Loop_setHwtHlsLoopID(*L, OrigHwtHlsLoopID);
	return LoopUnrollResult::PartiallyUnrolled;
}

const std::string StreamSegmentLoopUnrollPass::METADATA_NAME_io =
		"hwthls.loop.streamsegmentunroll.io";
const std::string StreamSegmentLoopUnrollPass::METADATA_NAME_allowSoFOnlyFor =
		"hwthls.loop.streamsegmentunroll.allowsofonlyfor";

llvm::PreservedAnalyses StreamSegmentLoopUnrollPass::run(llvm::Function &F,
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
	// F.dump();
	// writeCFGToDotFile(F, "tmp/StreamSegmentLoopUnrollPass.0.dot", AM, false,
	// 		true);
	// Add the loop nests in the reverse order of LoopInfo. See method
	// declaration.
	SmallPriorityWorklist<Loop*, 4> Worklist;
	appendLoopsToWorklist(LI, Worklist);
	std::vector<AllocaInst*> tmpAllocas;
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
		LoopUnrollResult Result = tryToUnrollStreamSegmentLoop(F, L, DT, LI,
				SE, TTI, AC, ORE, BFI, PSI,
				/*PreserveLCSSA*/true, UnrollOpts.OptLevel,
				UnrollOpts.OnlyWhenForced, UnrollOpts.ForgetSCEV, /*Count*/
				std::nullopt,
				/*Threshold*/std::nullopt, UnrollOpts.AllowPartial,
				UnrollOpts.AllowRuntime, UnrollOpts.AllowUpperBound,
				LocalAllowPeeling, UnrollOpts.AllowProfileBasedPeeling,
				UnrollOpts.FullUnrollMaxCount, tmpAllocas, AM);
		// DT.verify(DominatorTree::VerificationLevel::Full);
		if (Result != LoopUnrollResult::Unmodified) {
			// SE.forgetLoop(&L);
			SE.forgetAllLoops();
			Changed = true;
		}

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
	// writeCFGToDotFile(F, "tmp/StreamSegmentLoopUnrollPass.3.beforeReg2Mem.dot", AM,
	// 			false, false);
	// writeCFGToDotFile(F, "tmp/StreamSegmentLoopUnrollPass.3.cfg.dot", AM,
	// 		false, true);
 	llvm::PromoteMemToReg(tmpAllocas, DT, &AC);
	if (tmpAllocas.size()) {
		for (auto &BB : F) {
			// :note: llvm-21 PromoteMemToReg somehow generates phis with
			// reversed order of operands according to block predecessors
			sortPhiOperands(BB);
		}
	}
 	assert(DT.verify());
	//errs() << "\n";

 	// must recompute because rerouteLaneCfgAndSegmentValue currently does not update LI
 	// the LI may become invalid if L contains sub loops which are rerouted, they can be potentially
 	// merged together or with parent loop or they may become cycle
	PreservedAnalyses PA;
	PA.preserve<DominatorTreeAnalysis>();
	//PA.preserve<LoopAnalysis>();
	//PA.preserve<LoopAnalysisManagerFunctionProxy>();
	//PA.preserve<ScalarEvolutionAnalysis>();
 	AM.invalidate(F, PA);
	auto &LI2 = AM.getResult<LoopAnalysis>(F);
	auto &SE2 = AM.getResult<ScalarEvolutionAnalysis>(F);

	// assert(!verifyFunction(F, &errs()));
	//for (auto &L : LI2) {
 	//	L->dump();
 	//	errs() << "\n";
 	//}
//#ifndef NDEBUG
//	LI2.verify(DT);
//#endif
	for (const auto &L : LI2) {
		simplifyLoop(L, &DT, &LI2, &SE2, &AC, nullptr,
				false /* PreserveLCSSA */);
		formLCSSARecursively(*L, DT, &LI2, &SE2);
	}

	PA.preserve<LoopAnalysis>();
	PA.preserve<LoopAnalysisManagerFunctionProxy>();
	PA.preserve<ScalarEvolutionAnalysis>();
	return PA;
	// return getLoopPassPreservedAnalyses();
}

}
