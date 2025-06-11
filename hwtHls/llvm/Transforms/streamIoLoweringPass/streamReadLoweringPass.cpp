#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPass.h>
#include <algorithm>
#include <sstream>

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/TargetFolder.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPassPriv.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoRewriter.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

using namespace llvm;

namespace hwtHls {

class StreamReadRewriter: public StreamIoRewriter {
public:
	using StreamIoRewriter::StreamIoRewriter;
protected:
	void _rewriteAdtAccessToWordAccessInstruction(
			StreamIoDetector::HlsReadOrWrite *read) override;
	void _preparePrevWordVars(
			const std::vector<size_t> &possibleOffsets,
			std::pair<size_t, size_t> wordCntRange, bool readIsReliable,
			StreamIoDetector::HlsReadOrWrite *read,
			std::optional<StreamChannelWordValue> preLastWord,
			std::optional<StreamChannelWordValue> lastWord,
			llvm::SmallVector<StreamChannelWordValue> &prevWordVars);
	void _consumeReadWordsAndCreateResultData(
			const std::vector<size_t> &possibleOffsets,
			std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
			StreamIoDetector::HlsReadOrWrite *read,
			std::optional<StreamChannelWordValue> preLastWord,
			std::optional<StreamChannelWordValue> lastWord);
	void _handleOptionalReadsDependingOnCurrentOffset(
			const std::vector<size_t> &possibleOffsets,
			std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
			StreamIoDetector::HlsReadOrWrite *read);
	llvm::BasicBlock* _resetOffsetIfLast(llvm::StringRef name,
			llvm::Value *isLast, size_t elseValue);
};

void StreamReadRewriter::_handleOptionalReadsDependingOnCurrentOffset(
		const std::vector<size_t> &possibleOffsets,
		std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
		StreamIoDetector::HlsReadOrWrite *read) {

	auto _curOffsetVar = streamProps.getVarValue(Builder,
			streamProps.dataOffsetVar);

	llvm::SmallVector<Value*> offsetCaseCond;
	for (size_t off : possibleOffsets) {
		size_t wCnt = streamProps._getBusWordCntForChunk(off, chunkWidth);
		if (off == 0 || wCnt > wordCntRange.first) {
			//assert(wCnt == wordCntRange.first + 1);
			auto *offEn = Builder.CreateICmpEQ(_curOffsetVar,
					ConstantInt::get(_curOffsetVar->getType(),
							off % streamProps.dataWidth));
			offsetCaseCond.push_back(offEn);
		}
	}
	auto *extraReadEn = Builder.CreateOr(offsetCaseCond);
	if (!extraReadEn->getName().ends_with("(readEn)")) {
		extraReadEn->setName(extraReadEn->getName() + "(readEn)");
	}
	// original read should be moved to sequel
	// because now we are just preparing the data for it
	Instruction *thenBlockTerm = llvm::SplitBlockAndInsertIfThen(extraReadEn,
			read, false, /*BranchWeights*/nullptr, DTU, LI);
	Builder.SetInsertPoint(thenBlockTerm);
	auto *ioWordLd = Builder.CreateLoad(streamProps.segmentTy,
			streamProps.ioArg, /*isVolatile*/true, read->getName() + ".opt");
	streamProps.setAllData(Builder, ioWordLd);
	auto *subBB = dyn_cast<BasicBlock>(thenBlockTerm->getOperand(0));
	Builder.SetInsertPoint(subBB, BasicBlock::iterator(&subBB->front()));
}

llvm::BasicBlock* StreamReadRewriter::_resetOffsetIfLast(llvm::StringRef name,
		llvm::Value *isLast, size_t elseValue) {
	if (auto isLastConst = llvm::dyn_cast<ConstantInt>(isLast)) {
		if (isLastConst->getValue().getZExtValue()) {
			streamProps.setOffsetVar(Builder, 0);
		} else {
			streamProps.setOffsetVar(Builder, elseValue);
		}
		return Builder.GetInsertBlock();
	}
	Instruction *ThenTerm;
	Instruction *ElseTerm;
	llvm::SplitBlockAndInsertIfThenElse(isLast, &*Builder.GetInsertPoint(),
			&ThenTerm, &ElseTerm, nullptr, DTU);

	ThenTerm->getParent()->setName(name + "Last");
	Builder.SetInsertPoint(ThenTerm->getParent()->getTerminator());
	streamProps.setOffsetVar(Builder, 0);

	ElseTerm->getParent()->setName(name + "NoLast");
	Builder.SetInsertPoint(ElseTerm->getParent()->getTerminator());
	streamProps.setOffsetVar(Builder, elseValue);

	// just at the original place where we cut the original block
	// and inserted the optional IO operation before
	auto *sequelBlock = dyn_cast<BasicBlock>(ElseTerm->getOperand(0));
	Builder.SetInsertPoint(&sequelBlock->front());
	return sequelBlock;
}

void StreamReadRewriter::_preparePrevWordVars(
		const std::vector<size_t> &possibleOffsets,
		std::pair<size_t, size_t> wordCntRange, bool readIsReliable,
		StreamIoDetector::HlsReadOrWrite *read,
		std::optional<StreamChannelWordValue> preLastWord,
		std::optional<StreamChannelWordValue> lastWord,
		llvm::SmallVector<StreamChannelWordValue> &prevWordVars) {
	// fill reads for this chunk

	// There are several cases how to accommodate 3B chunk on 3B bus
	// |0|1|2|  // no prev word read (prevWordVars[1])
    //
	// | |0|1|  // prev word prevWordVars[0]
	// |2| | |  // new read prevWordVars[1] (stored to output prev word)
    //
	// | | |0|  // prev word prevWordVars[0]
	// |1|2| |  // new read prevWordVars[1] (stored to output prev word)

	// prevWordVars[0] = preLastWord
	// prevWordVars[1] = lastWord


	// due to different values of offset number of words may differ,
	// we obtain the max number of bus words for any offset, if some offset variant
	// requires +1 word, it is already loaded in
	// if true the read data is expected to always be present and well formated and no additional check is required

	// :note: preLastWord/lastWord are provided externally because its read is conditional on offset
	//   and this function construct only minimal number of reads shared for all variants
	assert(
			(wordCntRange.first == wordCntRange.second
					|| wordCntRange.first + 1 == wordCntRange.second)
					&& "max and min number of words for this chunk can be only (chunkWidth//dataWidth)(+1)");
	if (preLastWord.has_value())
		prevWordVars.push_back(preLastWord.value());
	if (lastWord.has_value())
		prevWordVars.push_back(lastWord.value());
	// :note: if this is the case which can read +1 words the load is already prepared before
	//     call of this function and is stored in streamProps tmp variables
	for (size_t i = 0; i < wordCntRange.first; ++i) {
		bool isFirstPartialWord = false;
		if (i == 0) {
			for (auto o : possibleOffsets) {
				if (o != 0) {
					isFirstPartialWord = true;
					break;
				}
			}
		}
		if (isFirstPartialWord) {
			// load previous last word if required (already added preLastWord/lastWord)
			// [todo] nonzero offset may also be directly behind SoF
		} else {
			// load next word from IO
			auto *ioWordLd = Builder.CreateLoad(streamProps.segmentTy,
					streamProps.ioArg, /*isVolatile*/true,
					read->getName() + ".r" + std::to_string(i));
			prevWordVars.push_back(
					StreamChannelWordValue::parseNativeWord(streamProps,
							Builder, ioWordLd));
		}
		bool isLast = i == wordCntRange.first - 1;
		if (isLast) {
			// store remainder of loaded word if required
			streamProps.setAllData(Builder, prevWordVars.back());
		} else if (readIsReliable) {
			// if this read is reliable and this is not last word set mask or empty to a constant meaning that all bytes of word are valid
			auto &w = prevWordVars.back();
			if (w.empty)
				w.empty = ConstantInt::get(w.empty->getType(), 0);
			if (w.mask)
				w.mask = ConstantInt::getAllOnesValue(w.mask->getType());
		} else {
			// create jump from read of this word to end of read which will implement skip of reads if the data is missing
			llvm_unreachable(
					"NotImplemented - skip of reads if input data underflow");
		}
	}
}

void StreamReadRewriter::_consumeReadWordsAndCreateResultData(
		const std::vector<size_t> &possibleOffsets,
		std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
		StreamIoDetector::HlsReadOrWrite *read,
		std::optional<StreamChannelWordValue> preLastWord,
		std::optional<StreamChannelWordValue> lastWord) {
	Builder.SetInsertPoint(read);
	bool readIsReliable = streamReadGetIsReliable(read);
	llvm::SmallVector<StreamChannelWordValue> prevWordVars;
	_preparePrevWordVars(possibleOffsets, wordCntRange, chunkWidth, read, lastWord, preLastWord, prevWordVars);
	auto *readResVar = Builder.CreateAlloca(read->getType(), nullptr,
			read->getName());
	streamProps.GeneratedAllocas.push_back(readResVar);
	std::vector<llvm::BasicBlock*> offsetBranches =
			_createBranchForEachOffsetVariant(possibleOffsets);

	auto off = possibleOffsets.begin();
	for (BasicBlock *br : offsetBranches) {
		if (br == read->getParent()) {
			Builder.SetInsertPoint(read);
		} else {
			Builder.SetInsertPoint(br,
					llvm::BasicBlock::iterator(&br->front()));
		}
		const auto DATA_WIDTH = streamProps.dataWidth;
		size_t end = *off + chunkWidth;
		size_t inWordOffset = *off % DATA_WIDTH;
		size_t _w = chunkWidth;
		size_t wordCnt = div_ceil(end == 0 ? 0 : end - 1, DATA_WIDTH);

		// resolve first word (chunkWords) used for this offset variant
		auto chunkWords = prevWordVars.begin();
		if ((wordCntRange.first != wordCntRange.second)
				&& streamProps._getBusWordCntForChunk(*off, chunkWidth)
						== wordCntRange.first) {
			// now not reading last word of predecessor but other offsets variant are using it
			++chunkWords; // the first word is optionally loaded and not loaded for this offset variant
			assert(prevWordVars.size() == wordCnt + 1);
		} else {
			assert(prevWordVars.size() == wordCnt);
		}
		// vector of parts to build replacement for value of this original ADT read
		llvm::SmallVector<StreamChannelWordValue> parts;
		for (; chunkWords != prevWordVars.end(); ++chunkWords) {
			assert(inWordOffset < DATA_WIDTH);
			size_t bitsToTake = std::min(_w, DATA_WIDTH - inWordOffset);
			auto partRead = *chunkWords;
			bool isLast = chunkWords == &prevWordVars.back();
			bool isGuaranteedToBeNotEoF = readIsReliable && !isLast;
			bool isGuarangeedToContainSomeData = readIsReliable;
			if (inWordOffset != 0) {
				// take from previous word
				// [todo] potentially can be None if the start of stream is not aligned
				partRead = partRead.slice(Builder, *off, bitsToTake,
						isGuaranteedToBeNotEoF, isGuarangeedToContainSomeData);
				inWordOffset = 0;
			} else {
				// read a new word
				if (bitsToTake != DATA_WIDTH) {
					//assert bitsToTake > 0, bitsToTake
					partRead = partRead.slice(Builder, inWordOffset, bitsToTake,
							isGuaranteedToBeNotEoF,
							isGuarangeedToContainSomeData);
				}
			}
			_w -= bitsToTake;
			parts.push_back(partRead);
		}
		llvm::Value *isFollowedByMoreValidData = nullptr;
		size_t newOffset = end % DATA_WIDTH;
		if (newOffset != 0) {
			switch (streamProps.byteEnableEncoding) {
			case ByteEnableEncoding::BEE_NONE:
				break;
			case ByteEnableEncoding::BEE_MASK: {
				auto maskOfLastWord = prevWordVars.back().mask;
				isFollowedByMoreValidData = CreateBitRangeGetConst(&Builder,
						maskOfLastWord, newOffset / 8, 1);
				break;
			}
			case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
				auto emptyOfLastWord = prevWordVars.back().empty;
				// size is larger than end of this section (newOffset)
				// = empty < bytesInWord - size
				size_t bytesInWord = streamProps.dataWidth
						/ streamProps.byteWidth;
				isFollowedByMoreValidData = Builder.CreateICmpULT(
						emptyOfLastWord,
						ConstantInt::get(emptyOfLastWord->getType(),
								bytesInWord - newOffset));
				break;
			}
			default:
				llvm_unreachable("invalid ByteEnableEncoding value");
			}
		}
		auto _readRes = StreamChannelWordValue::concat(Builder, parts);
		llvm::Value *readRes = _readRes.flatten(Builder,
				isFollowedByMoreValidData);
		assert(
				readRes->getType()->getIntegerBitWidth()
						== read->getType()->getIntegerBitWidth());
		if (!readRes->getName().contains(read->getName())) {
			readRes->setName(readRes->getName() + "(" + read->getName() + ")");
		}
		Builder.CreateStore(readRes, readResVar);

		if (newOffset == 0) {
			// last word for sure
			streamProps.setOffsetVar(Builder, 0);
		} else {
			// maybe last word
			// auto _sequelBlock =
			_resetOffsetIfLast(readRes->getName(), _readRes.eof, newOffset);
			//if (br == sequelBlock)
			//	sequelBlock = _sequelBlock;
		}
		//streamProps.setAllData(builder, prevWordVars.back());
		++off;
	}
	assert(read->getParent() != nullptr);
	//if (sequelBlock == read->getParent()) {
	// original read should always end up in sequel block because everything we generated should be before it
	Builder.SetInsertPoint(read);
	//} else {
	//	errs() << "builder.SetInsertPoint(sequelBlock\n";
	//	builder.SetInsertPoint(sequelBlock,
	//			BasicBlock::iterator(&sequelBlock->front()));
	//}
	// the insertion point should be the place behind all newly generated instructions which are implementing
	// original stream read pseudoinstruction
	auto *readRes = Builder.CreateLoad(read->getType(), readResVar,
			read->getName());
	read->replaceAllUsesWith(readRes);
}

void StreamReadRewriter::_rewriteAdtAccessToWordAccessInstruction(
		StreamIoDetector::HlsReadOrWrite *read) {
	bool readIsMarker = read == nullptr || IsStreamReadStartOfFrame(read)
			|| IsStreamReadEndOfFrame(read);
	const auto &possibleOffsets = cfg.inWordOffset[read];

	if (readIsMarker) {
		bool isStart = read != nullptr && IsStreamReadStartOfFrame(read);
		if (isStart) {
			if (possibleOffsets.size() != 1) {
				if (possibleOffsets.empty()) {
					throw std::runtime_error(
							"Can not find any offset of of which the frame may start");
				} else {
					std::string err;
					std::stringstream ss(err);
					ss
							<< "Use first word mask to resolve the offsetVar, possibleOffsets: [";
					for (size_t off : possibleOffsets) {
						ss << off << ", ";
					}
					ss << "]";

					// read words to satisfy initial offset
					throw std::runtime_error(ss.str());
				}
			} else {
				Builder.SetInsertPoint(read);
				streamProps.setOffsetVar(Builder, possibleOffsets[0]);
			}
		}
	} else {
		size_t chunkWidth = streamReadGetOrigChunkBitWidth(read);
		// if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
		// :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

		Builder.SetInsertPoint(read);
		// shared words for offset variants
		auto wordCntRange = streamProps._resolveMinMaxSegmentCount(
				possibleOffsets, chunkWidth);
		bool mayResultInDiffentNoOfWords = wordCntRange.first
				!= wordCntRange.second;
		if (!mayResultInDiffentNoOfWords) {
			// if this is a beginning of the frame and
			bool canFitInFirstWord = possibleOffsets[0] == 0
					&& chunkWidth <= cfg.DATA_WIDTH;
			if (canFitInFirstWord && possibleOffsets.size() > 1) {
				// this is a small chunk which fits to 1 word, but depending on offset we may require to load
				// the word from bus or reuse previous one
				mayResultInDiffentNoOfWords = true;
			}
		}

		std::optional<StreamChannelWordValue> preLastWord;
		std::optional<StreamChannelWordValue> lastWord;
		if (possibleOffsets.size() != 1 || possibleOffsets[0] != 0)
			lastWord = streamProps.getAllData(Builder);
		if (mayResultInDiffentNoOfWords) {
			preLastWord = lastWord;
			_handleOptionalReadsDependingOnCurrentOffset(possibleOffsets,
					wordCntRange, chunkWidth, read);
			lastWord = streamProps.getAllData(Builder);
		}
		// * collect/construct all reads common for every successor branch
		// * replace original read of ADT with a result composed of word reads
		_consumeReadWordsAndCreateResultData(possibleOffsets, wordCntRange,
				chunkWidth, read, lastWord, preLastWord);
	}
}

llvm::PreservedAnalyses StreamReadLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM) {
	auto *AC = FAM.getCachedResult<AssumptionAnalysis>(F);
	auto &DT = FAM.getResult<DominatorTreeAnalysis>(F);
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Eager);
	bool changed = false;
	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	auto streamProps = getStreamIoProps(F, GeneratedAllocas);
	auto &DL = F.getParent()->getDataLayout();

	// :note: copied from llvm-18 combineInstructionsOverFunction
	/// Builder - This is an IRBuilder that automatically inserts new
	/// instructions into the worklist when they are created.
	IRBuilder<TargetFolder, IRBuilderCallbackInserter> Builder(F.getContext(),
			TargetFolder(DL), IRBuilderCallbackInserter([AC](Instruction *I) {
				if (AC) {
					if (auto *Assume = dyn_cast<AssumeInst>(I))
						AC->registerAssumption(Assume);
				}
			})
	);

	for (StreamChannelProps &s : streamProps) {
		if (s.isOutput)
			continue;
		changed = true;
		StreamIoDetector cfg(s.dataWidth,
				reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(s.ios));
		cfg.detectIoAccessGraphs(F.getEntryBlock());
		cfg.resolvePossibleOffset();
		Builder.SetInsertPoint(F.getEntryBlock().getFirstNonPHI());
		s.createCommonVars(Builder);
		StreamReadRewriter srr(cfg, s, Builder, &DTU, nullptr);
		srr.rewriteAdtAccessToWordAccess(F.getEntryBlock());

		DTU.flush();
	}
	if (changed) {
		// errs() << "StreamReadLoweringPass.afer:\n" << F << "\n";
		std::string errTmp =
				"hwtHls::StreamReadLoweringPass corrupted function ";
		llvm::raw_string_ostream errSS(errTmp);
		errSS << F.getName().str();
		errSS << "\n";
		if (verifyModule(*F.getParent(), &errSS)) {
			throw std::runtime_error(errSS.str());
		}

		finalizeStreamIoLowerig(F, FAM, DT, streamProps, false,
				GeneratedAllocas);
		llvm::PreservedAnalyses PA;
		return PA;
	} else {
		return llvm::PreservedAnalyses::all();
	}
}

}
