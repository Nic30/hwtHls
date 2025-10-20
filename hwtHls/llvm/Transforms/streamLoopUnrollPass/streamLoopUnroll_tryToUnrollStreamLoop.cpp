#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnroll_tryToUnrollStreamLoop.h>

#include <llvm/Analysis/LoopIterator.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Transforms/Utils/LoopUtils.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelFormatInfo.h>
#include <hwtHls/llvm/Transforms/utils/loopHwtHlsMetadata.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/cfgFragmentStreamCopyLikeLoop.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnrollPass.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/cfgFragmentStreamCopyLikeLoop.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/sinkStreamWritesInLoop.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnroll_UnrollLoopStreamCopyLike.h>
#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnroll_tryAliginLoopBeginByPeeling.h>

#define DEBUG_TYPE "StreamLoopUnroll"
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(X) { X; }

using namespace llvm;

namespace hwtHls {

std::optional<StreamLoopUnrollArgs> StreamLoopUnrollArgs::getFromLoop(
		const llvm::Loop *TheLoop) {
	MDNode *MD = findOptionMDForHwtHlsLoop(TheLoop,
			StreamLoopUnrollPass::METADATA_NAME);
	if (!MD)
		return std::nullopt;
	assert(MD->getNumOperands() == 3);
	ConstantInt *ArgIMD = mdconst::extract_or_null<ConstantInt>(
			MD->getOperand(1).get());
	assert(ArgIMD);

	auto &F = *TheLoop->getHeader()->getParent();
	auto argI = ArgIMD->getZExtValue();
	assert(argI < F.arg_size());
	Argument &IoArg = *F.getArg(argI);

	ConstantInt *AlignMD = mdconst::extract_or_null<ConstantInt>(
			MD->getOperand(2).get());
	assert(AlignMD);

	return StreamLoopUnrollArgs { IoArg, bool(AlignMD->getZExtValue()) };
}

/*
 * Discover how many bits of stream are processed by a single iteration of the loop to resolve
 * */
void collectMinimalStreamProccessedBitWidthForLoop(Loop *L,
		const StreamChannelProps &streamProps,
		llvm::SetVector<size_t> &resSizes,
		llvm::SetVector<llvm::CallInst*> &resEntryStreamIos,
		size_t currentWidth, BasicBlock &B, BasicBlock::iterator curI) {
	assert(&B != nullptr);
	assert(
			L->isInnermost()
					&& "temporary assert we can allow subloops which do not process variable number of stream bits");
	assert(
			streamProps.ios.size()
					&& "streamProps.ios expected to be found in advance");
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
			// if not backedge or loop exit
			collectMinimalStreamProccessedBitWidthForLoop(L, streamProps,
					resSizes, resEntryStreamIos, currentWidth, *suc,
					suc->begin());
		} else {
			resSizes.insert(currentWidth);
		}
	}
}

void resolveBitsOfIterationsAndBeginOffsets(Function &F, Loop &L,
		StreamChannelProps &streamProps, SetVector<size_t> &entryOffsets,
		size_t &minNumberOfBitsProcessedPerIteration,
		llvm::SetVector<size_t> &minNumberOfBitsProcessedPerIterationVariants) {
	llvm::SetVector<llvm::CallInst*> entryStreamIos;
	collectMinimalStreamProccessedBitWidthForLoop(&L, streamProps,
			minNumberOfBitsProcessedPerIterationVariants, entryStreamIos, 0,
			*L.getHeader(), L.getHeader()->begin());
	minNumberOfBitsProcessedPerIteration = 0;
	for (auto bw : minNumberOfBitsProcessedPerIterationVariants) {
		if (bw > 0
				&& (minNumberOfBitsProcessedPerIteration == 0
						|| bw < minNumberOfBitsProcessedPerIteration))
			minNumberOfBitsProcessedPerIteration = bw;
	}
	if (minNumberOfBitsProcessedPerIteration == 0) {
		throw std::runtime_error(
				"StreamLoopUnrollPass: minimal number of stream bits processed per iteration must be >0");
	}
	StreamIoDetector cfg(nullptr, streamProps.dataWidth, streamProps.dataOffsetVar,
			reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(streamProps.ios));
	cfg.detectIoAccessGraphs(F.getEntryBlock());
	cfg.resolvePossibleOffset();
	if (entryStreamIos.size() != 1)
		throw std::runtime_error(
				"NotImplemented: StreamLoopUnrollPass multiple independent entry points to stream processing in loop body.");
	assert(streamProps.GeneratedAllocas.empty());
	for (auto *entryStreamI : entryStreamIos) {
		// we are looking at predecessors because we want to use offsets possible on entry of the loop
		// without offset variants generated from re-entry
		for (const CallInst *predStreamI : cfg.predecessors[entryStreamI]) {
			bool isReenterInLoop = L.contains(predStreamI);
			if (isReenterInLoop)
				continue;
			auto w = streamIoGetOrigChunkBitWidth(predStreamI);
			for (auto oOff : cfg.inWordOffset[predStreamI]) {
				size_t entryOff = (w + oOff) % streamProps.dataWidth;
				entryOffsets.insert(entryOff);
			}
		}
	}
}

// based on llvm LoopUnrollPass.cpp tryToUnrollLoop()
LoopUnrollResult tryToUnrollStreamLoop(llvm::Function &F, Loop *L,
		SimplifyQuery &SQ, DominatorTree &DT, LoopInfo *LI, ScalarEvolution &SE,
		const TargetLibraryInfo &TLI, const TargetTransformInfo &TTI,
		AssumptionCache &AC, OptimizationRemarkEmitter &ORE,
		BlockFrequencyInfo *BFI, ProfileSummaryInfo *PSI, bool PreserveLCSSA,
		int OptLevel, bool OnlyWhenForced, bool ForgetAllSCEV,
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
	auto _passArgs = StreamLoopUnrollArgs::getFromLoop(L);
	if (!_passArgs.has_value()) {
		LLVM_DEBUG(
				dbgs()
						<< "  Loop does not have hwthls.loop.streamunroll.io Attribute to enable this transformation.\n");
		// loop does not have Attribute to enable this transformation
		return LoopUnrollResult::Unmodified;
	}
	if (!L->isLoopSimplifyForm()) {
		LLVM_DEBUG(
				dbgs()
						<< "  Not unrolling loop which is not in loop-simplify form.\n");
		return LoopUnrollResult::Unmodified;
	}
	auto &passArgs = _passArgs.value();
	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	// get stream props for specified IoArg
	StreamChannelProps streamProps = findStreamIoPropsInMetadata(F,
			&passArgs.ioArg, GeneratedAllocas);

	streamProps.findStreamAccessInstructions();
	LoopBlocksRPO RPOT(L);
	RPOT.perform(LI);
	if (containsIrreducibleCFG<const BasicBlock*>(RPOT, *LI)) {
		throw std::runtime_error(
				"StreamLoopUnrollPass: NotImplemented: loop with irreducible CFG");
	}
	if (!L->getSubLoopsVector().empty()) {
		throw std::runtime_error(
				"StreamLoopUnrollPass: NotImplemented: has sub loops");
	}
	SetVector<size_t> entryOffsets;
	size_t minNumberOfBitsProcessedPerIteration = 0;
	llvm::SetVector<size_t> minNumberOfBitsProcessedPerIterationVariants;
	// first try to detect known patterns which can be unrolled directly without duplication of stream instructions
	resolveBitsOfIterationsAndBeginOffsets(F, *L, streamProps, entryOffsets,
			minNumberOfBitsProcessedPerIteration,
			minNumberOfBitsProcessedPerIterationVariants);
	auto cfgFragCopyLike = CfgFragmentStreamCopyLikeLoop::detect(SQ, SE, *L);
	LoopUnrollResult peelRes;
	// [todo] use cfgFragCopyLike if available
	peelRes = tryAliginLoopBeginByPeeling(DT, LI, SE, TLI, TTI, AC, ORE,
			PreserveLCSSA, streamProps, F, L, entryOffsets,
			minNumberOfBitsProcessedPerIteration,
			minNumberOfBitsProcessedPerIterationVariants);

	UnrollLoopOptions UP;
	UP.Count = div_ceil(streamProps.dataWidth, //- minEntryOffset,
			minNumberOfBitsProcessedPerIteration);
	UP.Force = true;
	UP.Runtime = true;
	UP.AllowExpensiveTripCount = true;
	UP.UnrollRemainder = true;
	UP.ForgetAllSCEV = ForgetAllSCEV;

	// Save loop properties before it is transformed.
	MDNode *OrigLoopID = L->getLoopID();
	L->setLoopID(nullptr);
	// Unroll the loop.
	Loop *RemainderLoop = nullptr;
	LoopUnrollResult UnrollResult = LoopUnrollResult::Unmodified;
	IRBuilder<> Builder(F.getContext());
	UnrollLoopOptions ULO = { UP.Count, UP.Force, UP.Runtime,
			UP.AllowExpensiveTripCount, UP.UnrollRemainder, ForgetAllSCEV };
	if (cfgFragCopyLike.has_value()) {
		UnrollResult = UnrollLoopStreamCopyLike(F, L, ULO, LI, &SE, &DT, &AC,
				&TTI, &ORE, PreserveLCSSA, cfgFragCopyLike.value(), Builder,
				streamProps, &RemainderLoop);
	}
	if (UnrollResult == LoopUnrollResult::Unmodified) {
		// if none of simple pattern has matched perform standard loop unrolling
		UnrollResult = UnrollLoop(L, ULO, LI, &SE, &DT, &AC, &TTI, &ORE,
				PreserveLCSSA, &RemainderLoop);
	}

	if (UnrollResult == LoopUnrollResult::Unmodified)
		return peelRes;

	if (RemainderLoop) {
		std::optional<MDNode*> RemainderLoopID = makeFollowupLoopID(OrigLoopID,
				{ LLVMLoopUnrollFollowupAll, LLVMLoopUnrollFollowupRemainder });
		if (RemainderLoopID)
			RemainderLoop->setLoopID(*RemainderLoopID);
	}

	if (UnrollResult != LoopUnrollResult::FullyUnrolled) {
		std::optional<MDNode*> _NewLoopID = makeFollowupLoopID(OrigLoopID, {
				LLVMLoopUnrollFollowupAll, LLVMLoopUnrollFollowupUnrolled });
		MDNode *NewLoopID =
				_NewLoopID.has_value() ? _NewLoopID.value() : nullptr;
		if (NewLoopID) {
			L->setLoopID(NewLoopID);
		}

		sinkStreamWritesInLoop(*L, SE, DT, *LI, AC, TLI, TTI, PreserveLCSSA);

		if (peelRes == LoopUnrollResult::PartiallyUnrolled)
			return LoopUnrollResult::PartiallyUnrolled;
		else
			return UnrollResult;
	}

	// If loop has an unroll count pragma or unrolled by explicitly set count
	// mark loop as unrolled to prevent unrolling beyond that requested.
	// [todo]

	return LoopUnrollResult::FullyUnrolled;
}

}
