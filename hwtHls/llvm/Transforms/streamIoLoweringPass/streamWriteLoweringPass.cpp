#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamWriteLoweringPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPassPriv.h>

#include <algorithm>

#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/DependenceAnalysis.h>
#include <llvm/Analysis/PostDominators.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Support/Casting.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/CodeMoverUtils.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamWriteEoFHoister.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoRewriter.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

using namespace llvm;

namespace hwtHls {

class StreamWriteRewriter: public StreamIoRewriter {
public:
	using StreamIoRewriter::StreamIoRewriter;

	// Create a write of curWordVar variable to output interface.
	void _insertIntfWrite(llvm::IRBuilder<> &builder) {
		auto w = streamProps.deparseNativeWord(builder);
		builder.CreateStore(w, streamProps.ioArg, /*isVolatile*/true);
		// wipe or reset processed values
		streamProps.setVarU64(builder, { }, streamProps.dataVar);
		streamProps.setDataMaskConst(builder, 0, 0);
		streamProps.setVarU64(builder, 0, streamProps.wDataPendingVar);
		streamProps.setVarU64(builder, 0, streamProps.dataLastVar);
		streamProps.setVarU64(builder, 0, streamProps.dataOffsetVar);
	}

	BasicBlock* _optionallyConsumePendingWord(llvm::IRBuilder<> &builder,
			llvm::Value *condition, StreamIoDetector::HlsReadOrWrite *write,
			llvm::Twine BlockLabel) {
		// write word from previous write because we just resolved it will not be last
		// the word itself is produced from previous write
		assert(
				dyn_cast<Instruction>(condition)
						&& "The value should not be constant, because "
								"if it is a constant it this should not be generated in the first place");
		// original read should be moved to sequel
		// because now we are just preparing the data for it
		Instruction *thenTerm = llvm::SplitBlockAndInsertIfThen(condition,
				&*builder.GetInsertPoint(), false, nullptr, DTU);
		auto *thenBb = thenTerm->getParent();
		thenBb->setName(BlockLabel);
		builder.SetInsertPoint(thenTerm);
		_insertIntfWrite(builder); // curWrite is there for dst and parent scope

		// :note: it is not required to write offset because it does not change
		// append read of new word
		auto *sequelBlock = dyn_cast<BranchInst>(thenTerm)->getSuccessor(0);
		builder.SetInsertPoint(&sequelBlock->front()); // just at the original place where we cut the original block and inserted the optional write before
		//streamProps.setVarU64(builder, 0, streamProps.wDataPendingVar);

		return sequelBlock;
	}

	void _rewriteAdtAccessToWordAccessInstruction(
			StreamIoDetector::HlsReadOrWrite *writeInst) override {
		bool writeIsMarker = writeInst == nullptr
				|| IsStreamWriteStartOfFrame(writeInst)
				|| IsStreamWriteEndOfFrame(writeInst);
		auto possibleOffsets = cfg.inWordOffset[writeInst];
		if (!possibleOffsets.size())
			throw std::runtime_error(
					"This is an accessible read, it should be already removed"); // , write
		auto &C = streamProps.ioArg->getContext();
		if (writeIsMarker) {
			if (writeInst == nullptr) {
			} else if (IsStreamWriteStartOfFrame(writeInst)) {
				IRBuilder<> builder(writeInst);
				// This is a beginning of the frame, we may have to set leading zeros in masks
				for (auto startOffset : possibleOffsets) {
					if (startOffset % 8 != 0) {
						throw std::runtime_error(
								"must be aligned to octet because Axi4Stream strb/keep works this way"); // (write, startOffset,
					}
				}
				if (possibleOffsets.size() != 1) {
					throw std::runtime_error(
							"Multiple positions of frame start"); // possibleOffsets
				} else {
					// reset or wipe variables with previous data
					streamProps.setVarU64(builder, 0,
							streamProps.wDataPendingVar);
					streamProps.setVarU64(builder, 0, streamProps.dataLastVar);
					streamProps.setDataMaskConst(builder, possibleOffsets[0],
							0);
					streamProps.setVarU64(builder, { }, streamProps.dataVar);
					streamProps.setVarU64(builder, possibleOffsets[0],
							streamProps.dataOffsetVar);
				}

			} else if (IsStreamWriteEndOfFrame(writeInst)) {
				IRBuilder<> builder(writeInst);
				// all writes which may be the last must be postponed until we reach this or other write
				// because we need to the value of signal "last" and value of masks if end is not aligned
				if (!dynamic_cast<StreamEoFMeta*>(cfg.ioInstrMeta[writeInst].get())->inlinedToPredecessors) {
					builder.SetInsertPoint(writeInst);
					for (auto endOffset : possibleOffsets) {
						if (endOffset % 8 != 0) {
							throw std::runtime_error(
									"must be aligned to octet because Axi4Stream strb/keep works this way"); // write, endOffset,
						}
					}
					// :note: remaining bits in mask should be set to 0 from the start
					streamProps.setVarU64(builder, 1, streamProps.dataLastVar);
					_insertIntfWrite(builder);
					streamProps.setVarU64(builder, 0,
							streamProps.wDataPendingVar);
				}
			} else {
				throw std::runtime_error("stream marker of unknown type");
			}

		} else {
			IRBuilder<> builder(writeInst);
			auto *src = writeInst->getArgOperand(1);
			auto width = src->getType()->getIntegerBitWidth();

			// if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
			// :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

			const auto DATA_WIDTH = streamProps.dataWidth;
			std::vector<llvm::BasicBlock*> offsetBranches = _createBranchForEachOffsetVariant(builder, possibleOffsets);

			// [todo] aggregate rewrite for all writes in this same block to reduce number of branches because of offset
			//   * writes may sink into common successor (may be beneficial to do this before LLVM to simplify code in advance to improve debugability)
			auto off = possibleOffsets.begin();
			for (BasicBlock *br : offsetBranches) {
				if (br == writeInst->getParent()) {
					builder.SetInsertPoint(writeInst);
				} else {
					builder.SetInsertPoint(&br->front());
				}
				bool endsWithConsumePendingOnLast = false;
				auto inWordOffset = *off % DATA_WIDTH;
				size_t srcOffset = 0;
				size_t end = *off + width;
				size_t wordCnt = div_ceil(end == 0 ? 0 : end - 1, DATA_WIDTH);
				// slice input part form original write input and write it to wordTmp variable
				for (size_t wordI = 0; wordI < wordCnt; wordI++) {
					bool last = wordI == wordCnt - 1;
					size_t availableBits = width - srcOffset;
					assert(DATA_WIDTH - inWordOffset);
					size_t bitsToTake = std::min(availableBits,
							DATA_WIDTH - inWordOffset);
					auto *_src = CreateBitRangeGetConst(&builder, src,
							srcOffset, bitsToTake);
					size_t dataHi = inWordOffset + bitsToTake;
					if (dataHi != DATA_WIDTH) {
						// pad with X to match DATA_WIDTH
						size_t paddingWidth = DATA_WIDTH - dataHi;
						auto *T = IntegerType::get(C, paddingWidth);
						_src = CreateBitConcat(&builder, { _src,
								UndefValue::get(T) });
					}

					if (wordI == 0 && *off == 0
							&& dynamic_cast<StreamChunkLastMeta*>(cfg.ioInstrMeta[writeInst].get())->prevWordMayBePending) {
						// if there is complete word pending, flush it because we just resolved the last flag (0)
						auto *_predWordPendingVar = streamProps.getVarValue(
								builder, streamProps.wDataPendingVar);
						_optionallyConsumePendingWord(builder,
								_predWordPendingVar, writeInst,
								writeInst->getName()
										+ "ConsumePendingRemainder");
					}
					// else it is guaranteed that there is "bitsToTake" bits in last word which we can fill

					// fill current chunk to current word
					streamProps.setDataMaskConst(builder,
							wordI == 0 ? *off : 0ul, bitsToTake);
					if (inWordOffset != 0 || dataHi != DATA_WIDTH) {
						streamProps.setData(builder, _src, inWordOffset);
						inWordOffset = 0;
					} else {
						builder.CreateStore(_src, streamProps.dataVar);
					}

					if (!last) {
						// write word somewhere in the middle of packet and in the middle of this chunk
						streamProps.setVarU64(builder, 0,
								streamProps.dataLastVar);
						_insertIntfWrite(builder);
						streamProps.setVarU64(builder, 0,
								streamProps.wDataPendingVar);
					} else {
						auto *meta =
								dynamic_cast<StreamChunkLastMeta*>(cfg.ioInstrMeta[writeInst].get());
						if (!meta->isLast.has_value()
								&& meta->isLastExpr == nullptr) {
							// this word must be written once we resolve next successor because it is not
							// possible to resolve last yet
							if (end % DATA_WIDTH == 0) {
								streamProps.setVarU64(builder, 1,
										streamProps.wDataPendingVar);
							}

						} else if (meta->isLast.has_value()) {
							// it is possible to resolve last, so we can output word immediately
							streamProps.setVarU64(builder, meta->isLast.value(),
									streamProps.dataLastVar);
							if (meta->isLast.value() || end % DATA_WIDTH == 0) {
								_insertIntfWrite(builder);
								streamProps.setVarU64(builder, 0,
										streamProps.wDataPendingVar);
							}

						} else {
							assert(meta->isLastExpr);
							// the condition for EoF is known in advance, we can use it and output word immediately
							builder.CreateStore(meta->isLastExpr,
									streamProps.dataLastVar);
							if (end % DATA_WIDTH == 0) {
								// if ending word always output word
								_insertIntfWrite(builder);
								streamProps.setVarU64(builder, 0,
										streamProps.wDataPendingVar);
							} else {
								// if not ending word output word only if isLast

								// write current offset in a specific branch (_optionallyConsumePendingWord may override it)
								streamProps.setOffsetVar(builder,
										end % DATA_WIDTH);
								endsWithConsumePendingOnLast = true;
								_optionallyConsumePendingWord(builder,
										meta->isLastExpr, writeInst,
										writeInst->getName()
												+ "ConsumePendingOnLast");
							}
						}
					}
					srcOffset += bitsToTake;
				}
				// write offset in a specific branch
				if (endsWithConsumePendingOnLast) {
					// end offset is already set
				} else {
					streamProps.setOffsetVar(builder, end % DATA_WIDTH);
				}
				++off;
			}
		}
	}
};

llvm::PreservedAnalyses StreamWriteLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM) {
	bool changed = false;
	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	auto streamProps = getStreamIoProps(F, GeneratedAllocas);

	auto &DT = FAM.getResult<DominatorTreeAnalysis>(F);
	auto &DI = FAM.getResult<DependenceAnalysis>(F);
	auto &PDT = FAM.getResult<PostDominatorTreeAnalysis>(F);
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
	//writeCFGToDotFile(F, "StreamWriteLoweringPass.before.dot", nullptr, nullptr);

	for (StreamChannelProps &s : streamProps) {
		if (!s.isOutput)
			continue;

		changed = true;
		StreamIoDetector cfg(s.dataWidth,
				reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(s.ios));
		cfg.detectIoAccessGraphs(F.getEntryBlock());
		cfg.resolvePossibleOffset();

		IRBuilder<> builder(F.getEntryBlock().getFirstNonPHI());
		s.createCommonVars(builder);
		s.createWDataPendingVar(builder);

		StreamWriteEoFHoister sweh(s, cfg, DT, PDT, DI);
		sweh.prepareLastExpressionForWrites();

		StreamWriteRewriter swr(cfg, s, &DTU, nullptr);
		swr.rewriteAdtAccessToWordAccess(F.getEntryBlock());
		DTU.flush();
	}
	if (changed) {
//		writeCFGToDotFile(F, "tmp/after.StreamWriteLoweringPass.dot", nullptr, nullptr);
		finalizeStreamIoLowerig(F, FAM, DT, streamProps, true,
				GeneratedAllocas);
		//throw std::runtime_error("[debug]");
		llvm::PreservedAnalyses PA;
		return PA;
	} else {
		return llvm::PreservedAnalyses::all();
	}
}

}
