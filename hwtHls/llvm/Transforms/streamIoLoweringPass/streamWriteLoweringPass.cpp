#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamWriteLoweringPass.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPassPriv.h>

#include <algorithm>

#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/DependenceAnalysis.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Dominators.h>
#include <llvm/Support/Casting.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Transforms/Utils/CodeMoverUtils.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoRewriter.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

// #include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

using namespace llvm;

namespace hwtHls {

class StreamWriteRewriter: public StreamIoRewriter {
public:
	using StreamIoRewriter::StreamIoRewriter;

	// Create a write of curWordVar variable to output interface.
	void _insertIntfWrite() {
		auto w = streamProps.deparseNativeWord(Builder);
		Builder.CreateStore(w, streamProps.ioArg, /*isVolatile*/true);
		// wipe or reset processed values
		streamProps.setVarU64(Builder, { }, streamProps.dataVar);
		streamProps.setDataMaskOrEmptyConst(Builder, 0, 0);
		streamProps.setVarU64(Builder, 0, streamProps.wDataPendingVar);

		if (streamProps.dataSoFVar)
			streamProps.setVarU64(Builder, 0, streamProps.dataSoFVar);
		if (streamProps.dataEoFVar)
			streamProps.setVarU64(Builder, 0, streamProps.dataEoFVar);
		if (streamProps.dataOffsetVar)
			streamProps.setVarU64(Builder, 0, streamProps.dataOffsetVar);
	}

	BasicBlock* _optionallyConsumePendingWord(llvm::Value *condition,
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
				&*Builder.GetInsertPoint(), false, nullptr, DTU);
		auto *thenBb = thenTerm->getParent();
		thenBb->setName(BlockLabel);
		Builder.SetInsertPoint(thenTerm);
		_insertIntfWrite(); // curWrite is there for dst and parent scope

		// :note: it is not required to write offset because it does not change
		// append read of new word
		auto *sequelBlock = dyn_cast<BranchInst>(thenTerm)->getSuccessor(0);
		Builder.SetInsertPoint(&sequelBlock->front()); // just at the original place where we cut the original block and inserted the optional write before
		//streamProps.setVarU64(builder, 0, streamProps.wDataPendingVar);

		return sequelBlock;
	}

	BasicBlock* _flushIfHasEoF(Value *writeEoF, llvm::Twine BlockLabel) {
		auto BB = _optionallyConsumePendingWord(writeEoF,
				streamProps.ioArg->getName() + BlockLabel);
		streamProps.setVarU64(Builder, 0, streamProps.dataEoFVar);
		return BB;
	}

	void _rewriteAdtAccessToWordAccessInstructionSofAndEof(
			const std::vector<size_t> &possibleOffsets,
			StreamIoDetector::HlsReadOrWrite *inst) {
		if (inst == nullptr) {
		} else if (IsStreamWriteStartOfFrame(inst)) {
			// This is a beginning of the frame, we may have to set leading zeros in masks
			Builder.SetInsertPoint(inst);
			for (auto startOffset : possibleOffsets) {
				if (startOffset % streamProps.byteWidth != 0) {
					throw std::runtime_error(
							"must be aligned to byte width because strb/keep/empty works this way"); // (write, startOffset,
				}
			}
			if (possibleOffsets.size() != 1) {
				throw std::runtime_error("Multiple positions of frame start"); // possibleOffsets
			} else {
				// reset or wipe variables with previous data
				streamProps.commonVarsInitialize(Builder);
				streamProps.setDataMaskOrEmptyConst(Builder, possibleOffsets[0],
						0);
				streamProps.setVarU64(Builder, possibleOffsets[0],
						streamProps.dataOffsetVar);
			}
		} else if (IsStreamWriteEndOfFrame(inst)) {
			// delete content of all tmp variables to prevent false dependencies
			Builder.SetInsertPoint(inst);
			for (auto var : { streamProps.dataEnableVar, //
					streamProps.dataVar,      //
					streamProps.dataMaskVar,  //
					streamProps.dataErrorVar, //
					streamProps.dataSoFVar,   //
					streamProps.dataEoFVar,   //
					streamProps.dataEmptyVar }) {
				if (var)
					streamProps.setVarU64(Builder, { }, var);
			}
		} else {
			throw std::runtime_error("stream marker of unknown type");
		}
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
			_rewriteAdtAccessToWordAccessInstructionSofAndEof(possibleOffsets,
					writeInst);
		} else {
			Builder.SetInsertPoint(writeInst);
			auto *src = writeInst->getArgOperand(1);
			Value *writeMaskOrEmpty = streamWriteGetWriteMaskOrEmpty(writeInst);
			Value *writeEoF = streamWriteGetWriteEoF(writeInst);
			std::optional<bool> writeEoFasConst;
			if (auto C = dyn_cast<ConstantInt>(writeEoF)) {
				writeEoFasConst = C->getValue().getZExtValue();
			}
			auto widthOfWrite = src->getType()->getIntegerBitWidth();

			// if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
			// :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

			const auto DATA_WIDTH = streamProps.dataWidth;
			std::vector<llvm::BasicBlock*> offsetBranches =
					_createBranchForEachOffsetVariant(possibleOffsets);

			// [todo] aggregate rewrite for all writes in this same block to reduce number of branches because of offset
			//   * writes may sink into common successor (may be beneficial to do this before LLVM to simplify code in advance to improve debuggability)
			auto off = possibleOffsets.begin();
			for (BasicBlock *br : offsetBranches) {
				if (br == writeInst->getParent()) {
					Builder.SetInsertPoint(writeInst);
				} else {
					Builder.SetInsertPoint(&br->front());
				}
				auto inWordOffset = *off % DATA_WIDTH;
				size_t srcOffset = 0; // position in the bits of written value
				size_t end = *off + widthOfWrite;
				size_t wordCnt = div_ceil(end == 0 ? 0 : end - 1, DATA_WIDTH);
				// slice input part form original write input and write it to wordTmp variable
				for (size_t wordI = 0; wordI < wordCnt; wordI++) {
					bool isLastWordOfChunk = wordI == wordCnt - 1;
					size_t availableBits = widthOfWrite - srcOffset;
					assert(DATA_WIDTH - inWordOffset);
					size_t bitsToTake = std::min(availableBits,
							DATA_WIDTH - inWordOffset);
					auto *_src = CreateBitRangeGetConst(&Builder, src,
							srcOffset, bitsToTake);
					size_t dataHi = inWordOffset + bitsToTake;
					bool curWordIsCompleted = dataHi == DATA_WIDTH;
					if (!curWordIsCompleted) {
						// pad with X to match DATA_WIDTH
						size_t paddingWidth = DATA_WIDTH - dataHi;
						auto *T = IntegerType::get(C, paddingWidth);
						_src = CreateBitConcat(&Builder, { _src,
								UndefValue::get(T) });
					}

					// else it is guaranteed that there is "bitsToTake" bits in last word which we can fill

					// fill current chunk to current word
					auto inChunkOffset = wordI == 0 ? *off : 0ul;
					streamProps.setDataMaskOrEmpty(Builder, widthOfWrite,
							srcOffset, inChunkOffset, bitsToTake,
							writeMaskOrEmpty);
					if (inWordOffset != 0 || !curWordIsCompleted) {
						// handle the first word where the beginning does not need to be aligned
						streamProps.setData(Builder, _src, inWordOffset);
						inWordOffset = 0;
					} else {
						Builder.CreateStore(_src, streamProps.dataVar);
					}
					if (isLastWordOfChunk) {
						// handle flushing/staging of the last word
						if (writeEoFasConst.has_value()) {
							streamProps.setVarU64(Builder,
									writeEoFasConst.value(),
									streamProps.dataEoFVar);
							if (!writeEoFasConst.value()
									&& all_of(cfg.cfg[writeInst],
											[](
													std::pair<size_t,
															const CallInst*> suc) {
												return IsStreamWriteEndOfFrame(
														suc.second);
											})) {
								throw std::runtime_error(
										"StreamWrite is followed only by StreamWriteEndOfFrame but does not have EoF flag set, this would result in broken framing");
							}
							if (writeEoFasConst.value() || curWordIsCompleted) {
								_insertIntfWrite();
							}
						} else {
							Builder.CreateStore(writeEoF,
									streamProps.dataEoFVar);
							if (curWordIsCompleted) {
								// has a complete word to write
								_insertIntfWrite();
							} else {
								// may have complete word to write or a word with last
								// or incomplete word which must wait for next write data
								_optionallyConsumePendingWord(writeEoF,
										streamProps.ioArg->getName()
												+ "ConsumePendingOnLast");
								streamProps.setOffsetVar(Builder,
										end % DATA_WIDTH);
							}
						}
					} else {
						// write a complete word somewhere in the middle of packet and in the middle of this chunk
						streamProps.setVarU64(Builder, 0,
								streamProps.dataEoFVar);
						_insertIntfWrite();
					}
					srcOffset += bitsToTake;
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
    LazyValueInfo *LVI = nullptr;
	auto &DT = FAM.getResult<DominatorTreeAnalysis>(F);
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
	// writeCFGToDotFile(F, "tmp/StreamWriteLoweringPass.before.dot", FAM);

	for (StreamChannelProps &s : streamProps) {
		if (!s.isOutput)
			continue;

		changed = true;
		if (s.dataOffsetVar && !LVI )
			LVI = &FAM.getResult<LazyValueAnalysis>(F);
		StreamIoDetector cfg(LVI, s.dataWidth, s.dataOffsetVar,
				reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(s.ios));
		cfg.detectIoAccessGraphs(F.getEntryBlock());
		cfg.resolvePossibleOffset();
		if (LVI)
			LVI->clear();

		IRBuilder<> builder(F.getEntryBlock().getFirstNonPHI());
		s.createCommonVars(builder);
		s.createWDataPendingVar(builder);
		// writeCFGToDotFile(F, "tmp/StreamWriteLoweringPass.before.dot", FAM);

		StreamWriteRewriter swr(cfg, s, builder, &DTU, nullptr);
		swr.rewriteAdtAccessToWordAccess(F.getEntryBlock());
		DTU.flush();
	}
	if (changed) {
		// writeCFGToDotFile(F, "tmp/StreamWriteLoweringPass.after.dot", FAM);
		finalizeStreamIoLowerig(F, FAM, DT, streamProps, true,
				GeneratedAllocas);
		llvm::PreservedAnalyses PA;
		return PA;
	} else {
		return llvm::PreservedAnalyses::all();
	}
}

}
