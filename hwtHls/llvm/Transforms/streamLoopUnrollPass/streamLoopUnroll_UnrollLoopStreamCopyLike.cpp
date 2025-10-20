#include <hwtHls/llvm/Transforms/streamLoopUnrollPass/streamLoopUnroll_UnrollLoopStreamCopyLike.h>

#include <hwtHls/llvm/targets/intrinsic/streamIo.h>

using namespace llvm;

namespace hwtHls {

llvm::LoopUnrollResult UnrollLoopStreamCopyLike(llvm::Function &F,
		llvm::Loop *L, llvm::UnrollLoopOptions ULO, llvm::LoopInfo *LI,
		llvm::ScalarEvolution *SE, llvm::DominatorTree *DT,
		llvm::AssumptionCache *AC, const llvm::TargetTransformInfo *TTI,
		llvm::OptimizationRemarkEmitter *ORE, bool PreserveLCSSA,
		CfgFragmentStreamCopyLikeLoop &cpFrag, llvm::IRBuilder<> &Builder,
		StreamChannelProps &streamProps, llvm::Loop **RemainderLoop) {
	StreamChannelProps *streamPropsForRead = nullptr;
	StreamChannelProps *streamPropsForWrite = nullptr;
	if (cpFrag.read && streamProps.ioArg == streamReadGetIoArg(cpFrag.read)) {
		streamPropsForRead = &streamProps;
	} else if (cpFrag.write
			&& streamProps.ioArg == streamWriteGetIoArg(cpFrag.write)) {
		streamPropsForWrite = &streamProps;
	}
	assert(streamPropsForRead || streamPropsForWrite);

	if (cpFrag.read && !cpFrag.write) {
		BasicBlock *exitBB;
		if (cpFrag.isExactlyReadUntilEof(*streamPropsForRead, exitBB)) {
			if (cpFrag.readUntilEofContainsNoAdditionalInstructions()) {
				size_t width = streamReadGetOrigChunkBitWidth(cpFrag.read);
				Builder.SetInsertPoint(cpFrag.read);
				size_t newChunkBitWidth = width * ULO.Count;
				bool newIsReliable = false;
				size_t newReturnBitWidth =
						streamPropsForRead->getReadReturnWidth(newChunkBitWidth,
								newIsReliable);
				auto newRead = CreateStreamRead(&Builder,
						streamPropsForRead->ioArg, newChunkBitWidth,
						newReturnBitWidth, newIsReliable);

				newRead->takeName(cpFrag.read);
				Value *isEoF = streamPropsForRead->streamReadGetEoF(Builder,
						newRead);
				auto &BB = *cpFrag.read->getParent();
				auto br = dyn_cast<BranchInst>(BB.getTerminator());
				assert(br && br->isConditional());
				br->setCondition(isEoF);
				if (cpFrag.blockInstructionsHaveExternalUsers()) {
					llvm_unreachable(
							"[todo] not implemented reroute external uses of the read values");
				}
				BB.erase(cpFrag.read->getIterator(), br->getIterator());
				return llvm::LoopUnrollResult::PartiallyUnrolled;
			}
		}
	} else if (cpFrag.read && cpFrag.write) {
		llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
		StreamChannelProps otherStreamProps = findStreamIoPropsInMetadata(F,
				streamPropsForRead ?
						streamWriteGetIoArg(cpFrag.write) :
						streamReadGetIoArg(cpFrag.read), GeneratedAllocas);
		if (streamPropsForRead) {
			streamPropsForWrite = &otherStreamProps;
		} else {
			streamPropsForRead = &otherStreamProps;
		}

		BasicBlock *exitBB;
		if (cpFrag.isExactlyJustCopy(*streamPropsForRead, *streamPropsForWrite,
				exitBB)) {
			if (cpFrag.justCopyContainsOnlyInstructionsForCopy()) {
				// remove current body and construct wider read and write
				size_t width =
						streamWriteGetWriteData(cpFrag.write)->getType()->getIntegerBitWidth();
				Builder.SetInsertPoint(cpFrag.read);
				size_t newChunkBitWidth = width * ULO.Count;
				bool newIsReliable = false;
				size_t newReturnBitWidth =
						streamPropsForRead->getReadReturnWidth(newChunkBitWidth,
								newIsReliable);
				auto streamPropsForReadActualSize = streamPropsForRead->resize(
						newChunkBitWidth, newIsReliable,
						newIsReliable ?
								ByteEnableEncoding::BEE_NONE :
								streamPropsForRead->byteEnableEncoding);

				auto newRead = CreateStreamRead(&Builder,
						streamPropsForRead->ioArg, newChunkBitWidth,
						newReturnBitWidth, newIsReliable);
				newRead->takeName(cpFrag.read);
				auto valueToWrite = streamPropsForRead->streamReadGetData(
						Builder, newRead);
				Value *writeMaskOrEmpty = nullptr;
				assert(
						streamPropsForRead->byteEnableEncoding
								== streamPropsForWrite->byteEnableEncoding);
				switch (streamPropsForReadActualSize.byteEnableEncoding) {
				case ByteEnableEncoding::BEE_NONE:
				case ByteEnableEncoding::BEE_MASK: {
					if (streamPropsForReadActualSize.hasMask())
						writeMaskOrEmpty =
								streamPropsForReadActualSize.streamReadGetMask(
										Builder, newRead);
					break;
				}
				case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
					if (streamPropsForReadActualSize.hasEmpty())
						writeMaskOrEmpty =
								streamPropsForReadActualSize.streamReadGetEmpty(
										Builder, newRead);
					break;
				}
				default:
					llvm_unreachable(
							"Invalid value for byte enable encoding of a stream");
				}
				Value *isSoF = nullptr;
				if (streamPropsForRead->hasSoF())
					isSoF = streamPropsForReadActualSize.streamReadGetSoF(
							Builder, newRead);
				Value *isEoF = streamPropsForReadActualSize.streamReadGetEoF(
						Builder, newRead);
				CreateStreamWrite(&Builder, streamPropsForWrite->ioArg,
						valueToWrite, writeMaskOrEmpty, isSoF, isEoF);
				auto &BB = *cpFrag.read->getParent();
				auto br = dyn_cast<BranchInst>(BB.getTerminator());
				assert(br && br->isConditional());
				br->setCondition(isEoF);
				if (cpFrag.blockInstructionsHaveExternalUsers()) {
					llvm_unreachable(
							"[todo] not implemented reroute external uses of the read values");
				}
				for (Instruction& I: make_early_inc_range(make_range(
						br->getPrevNode()->getReverseIterator(),
						cpFrag.read->getPrevNode()->getReverseIterator()))) {
					I.eraseFromParent();
				}
				// Can not just use BB.erase because it would erase from the beginning
				// which means that all successors would be temporally left with broken uses
				// BB.erase(cpFrag.read->getIterator(), br->getIterator());
				return llvm::LoopUnrollResult::PartiallyUnrolled;
			} else {
				llvm_unreachable("[todo] not implemented");
			}
		}
	}
	return llvm::LoopUnrollResult::Unmodified;
}

}
