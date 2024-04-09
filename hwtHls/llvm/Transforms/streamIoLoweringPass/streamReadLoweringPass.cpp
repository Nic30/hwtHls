#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPass.h>
#include <algorithm>
#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoInstrCollector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPassPriv.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoRewriter.h>

using namespace llvm;

namespace hwtHls {

class StreamReadRewriter: public StreamIoRewriter {
public:
	using StreamIoRewriter::StreamIoRewriter;
protected:
	void _rewriteAdtAccessToWordAccessInstruction(
			StreamIoDetector::HlsReadOrWrite *read) override;
	void _consumeReadWordsAndCreateResultData(llvm::IRBuilder<> &builder,
			const std::vector<size_t> &possibleOffsets,
			std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
			StreamIoDetector::HlsReadOrWrite *read);
	void _handleOptionalReadsDependingOnCurrentOffset(IRBuilder<> &builder,
			const std::vector<size_t> &possibleOffsets,
			std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
			StreamIoDetector::HlsReadOrWrite *read);
	llvm::BasicBlock* _resetOffsetIfLast(IRBuilder<> &builder,
			llvm::StringRef name, llvm::Value *isLast, size_t elseValue);
};

void StreamReadRewriter::_handleOptionalReadsDependingOnCurrentOffset(
		IRBuilder<> &builder, const std::vector<size_t> &possibleOffsets,
		std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
		StreamIoDetector::HlsReadOrWrite *read) {

	auto _curOffsetVar = streamProps.getVarValue(builder,
			streamProps.dataOffsetVar);

	llvm::SmallVector<Value*> offsetCaseCond;
	for (size_t off : possibleOffsets) {
		size_t wCnt = streamProps._getBusWordCntForChunk(off, chunkWidth);
		if (off == 0 || wCnt > wordCntRange.first) {
			//assert(wCnt == wordCntRange.first + 1);
			auto *offEn = builder.CreateICmpEQ(_curOffsetVar,
					ConstantInt::get(_curOffsetVar->getType(),
							off % streamProps.dataWidth));
			offsetCaseCond.push_back(offEn);
		}
	}
	auto *extraReadEn = builder.CreateOr(offsetCaseCond);
	if (!extraReadEn->getName().ends_with("(readEn)")) {
		extraReadEn->setName(extraReadEn->getName() + "(readEn)");
	}
	// original read should be moved to sequel
	// because now we are just preparing the data for it
	Instruction *thenBlockTerm = llvm::SplitBlockAndInsertIfThen(extraReadEn,
			read, false, /*BranchWeights*/nullptr, DTU, LI);
	builder.SetInsertPoint(thenBlockTerm);
	auto *ioWordLd = builder.CreateLoad(streamProps.nativeWordTy,
			streamProps.ioArg, /*isVolatile*/true);
	streamProps.setAllData(builder, ioWordLd);
	auto *subBB = dyn_cast<BasicBlock>(thenBlockTerm->getOperand(0));
	builder.SetInsertPoint(subBB, BasicBlock::iterator(&subBB->front()));
}

llvm::BasicBlock* StreamReadRewriter::_resetOffsetIfLast(IRBuilder<> &builder,
		llvm::StringRef name, llvm::Value *isLast, size_t elseValue) {
	if (auto isLastConst = llvm::dyn_cast<ConstantInt>(isLast)) {
		if (isLastConst->getValue().getZExtValue()) {
			streamProps.setOffsetVar(builder, 0);
		} else {
			streamProps.setOffsetVar(builder, elseValue);
		}
		return builder.GetInsertBlock();
	}
	Instruction *ThenTerm;
	Instruction *ElseTerm;
	llvm::SplitBlockAndInsertIfThenElse(isLast, &*builder.GetInsertPoint(),
			&ThenTerm, &ElseTerm, nullptr, DTU);

	ThenTerm->getParent()->setName(name + "Last");
	builder.SetInsertPoint(ThenTerm->getParent()->getTerminator());
	streamProps.setOffsetVar(builder, 0);

	ElseTerm->getParent()->setName(name + "NoLast");
	builder.SetInsertPoint(ElseTerm->getParent()->getTerminator());
	streamProps.setOffsetVar(builder, elseValue);

	// just at the original place where we cut the original block
	// and inserted the optional IO operation before
	auto *sequelBlock = dyn_cast<BasicBlock>(ElseTerm->getOperand(0));
	builder.SetInsertPoint(&sequelBlock->front());
	return sequelBlock;
}

void StreamReadRewriter::_consumeReadWordsAndCreateResultData(
		llvm::IRBuilder<> &builder, const std::vector<size_t> &possibleOffsets,
		std::pair<size_t, size_t> wordCntRange, size_t chunkWidth,
		StreamIoDetector::HlsReadOrWrite *read) {
	llvm::SmallVector<StreamChannelWordValue> prevWordVars;
	// fill reads for this chunk
	// due to different values of offset this number of words may differ,
	// we obtain the minimal number of bus words and we may requre additional
	// read from IO for some offsets
	builder.SetInsertPoint(read);
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
			// load previous last word if required
			// [todo] nonzero offset may also be directly behind SoF
			prevWordVars.push_back(streamProps.getAllData(builder));
		} else {
			// load next word from IO
			auto *ioWordLd = builder.CreateLoad(streamProps.nativeWordTy,
					streamProps.ioArg, /*isVolatile*/true);
			prevWordVars.push_back(
					streamProps.parseNativeWord(builder, ioWordLd));
			bool isLast = i == wordCntRange.first - 1;
			if (isLast) {
				// store remainder of loaded word if required
				streamProps.setAllData(builder, prevWordVars.back());
			}
		}
	}
	// errs() << "StreamReadRewriter::_consumeReadWordsAndCreateResultData: " << *read << " <" << wordCntRange.first << "," << wordCntRange.second << ">\n";
	// errs() << "    offsets:";
	// for (auto o: possibleOffsets) {
	// 	errs() << " " << o;
	// }
	// errs() << "\n";
	;
	auto *readResVar = builder.CreateAlloca(read->getType(), nullptr,
			read->getName());
	streamProps.GeneratedAllocas.push_back(readResVar);
	std::vector<llvm::BasicBlock*> offsetBranches = _createBranchForEachOffsetVariant(
			builder, possibleOffsets);

	auto off = possibleOffsets.begin();
	for (BasicBlock *br : offsetBranches) {
		if (br == read->getParent()) {
			builder.SetInsertPoint(read);
		} else {
			builder.SetInsertPoint(br,
					llvm::BasicBlock::iterator(&br->front()));
		}
		const auto DATA_WIDTH = streamProps.dataWidth;
		size_t end = *off + chunkWidth;
		size_t inWordOffset = *off % DATA_WIDTH;
		size_t _w = chunkWidth;
		size_t wordCnt = div_ceil(end == 0 ? 0 : end - 1, DATA_WIDTH);

		// resolve first word (chunkWords) used for this offset variant
		auto chunkWords = prevWordVars.begin();
		if (inWordOffset == 0 && (wordCntRange.first != wordCntRange.second)
				&& streamProps._getBusWordCntForChunk(*off, chunkWidth)
						== wordCntRange.first) {
			// now not reading last word of predecessor but other offsets variant are using it
			++chunkWords;
			assert(prevWordVars.size() == wordCnt - 1);
		} else {
			assert(prevWordVars.size() == wordCnt);
		}
		// vector of parts to build replacement for value of this original ADT read
		llvm::SmallVector<StreamChannelWordValue> parts;
		//size_t wordI = 0;
		for (; chunkWords != prevWordVars.end(); ++chunkWords) {
			assert(inWordOffset < DATA_WIDTH);
			size_t bitsToTake = std::min(_w, DATA_WIDTH - inWordOffset);
			auto partRead = *chunkWords;
			if (inWordOffset != 0) {
				// take from previous word
				// [todo] potentially can be None if the start of stream is not aligned
				partRead = partRead.slice(builder, *off, bitsToTake);
				inWordOffset = 0;
			} else {
				// read a new word
				if (bitsToTake != DATA_WIDTH) {
					//assert bitsToTake > 0, bitsToTake
					partRead = partRead.slice(builder, inWordOffset,
							bitsToTake);
				}
			}
			_w -= bitsToTake;
			parts.push_back(partRead);
		}

		auto _readRes = StreamChannelWordValue::concat(builder, parts);
		llvm::Value *readRes = _readRes.flatten(builder);
		assert(
				readRes->getType()->getIntegerBitWidth()
						== read->getType()->getIntegerBitWidth());
		if (!readRes->getName().contains(read->getName())) {
			readRes->setName(readRes->getName() + "(" + read->getName() + ")");
		}
		builder.CreateStore(readRes, readResVar);
		size_t newOffset = end % DATA_WIDTH;

		if (newOffset == 0) {
			// last word for sure
			streamProps.setOffsetVar(builder, 0);
		} else {
			// maybe last word
			// auto _sequelBlock =
			_resetOffsetIfLast(builder, readRes->getName(), _readRes.last,
					newOffset);
			//if (br == sequelBlock)
			//	sequelBlock = _sequelBlock;
		}
		//streamProps.setAllData(builder, prevWordVars.back());
		++off;
	}
	assert(read->getParent() != nullptr);
	//if (sequelBlock == read->getParent()) {
	// original read should always end up in sequel block because everything we generated should be before it
	builder.SetInsertPoint(read);
	//} else {
	//	errs() << "builder.SetInsertPoint(sequelBlock\n";
	//	builder.SetInsertPoint(sequelBlock,
	//			BasicBlock::iterator(&sequelBlock->front()));
	//}
	// the insertion point should be the place behind all newly generated instructions which are implementing
	// original stream read pseudoinstruction
	auto *readRes = builder.CreateLoad(read->getType(), readResVar,
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
				// read words to satisfy initial offset
				throw std::runtime_error(
						"Use first word mask to resolve the offsetVar");
			} else {
				IRBuilder<> builder(read);
				streamProps.setOffsetVar(builder, possibleOffsets[0]);
			}
		}
	} else {
		size_t chunkWidth = streamReadGetOrigChunkBitWidth(read);
		// if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
		// :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

		IRBuilder<> builder(read);
		// shared words for offset variants
		auto wordCntRange = streamProps._resolveMinMaxWordCount(possibleOffsets,
				chunkWidth);
		bool mayResultInDiffentNoOfWords = wordCntRange.first
				!= wordCntRange.second;
		if (!mayResultInDiffentNoOfWords) {
			// if this is a beginning of the frame and
			bool canFitInFirstWord = possibleOffsets[0] == 0 && chunkWidth <= cfg.DATA_WIDTH;
			if (canFitInFirstWord && possibleOffsets.size() > 1) {
				// this is a small chunk which fits to 1 word, but depending on offset we may require to load
				// the word from bus or reuse previous one
				mayResultInDiffentNoOfWords = true;
			}
		}
		if (mayResultInDiffentNoOfWords) {
			_handleOptionalReadsDependingOnCurrentOffset(builder,
					possibleOffsets, wordCntRange, chunkWidth, read);
		}
		// * collect/construct all reads common for every successor branch
		// * replace original read of ADT with a result composed of word reads
		_consumeReadWordsAndCreateResultData(builder, possibleOffsets,
				wordCntRange, chunkWidth, read);
	}
}

llvm::PreservedAnalyses StreamReadLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM) {
	auto &DT = FAM.getResult<DominatorTreeAnalysis>(F);
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Eager);
	bool changed = false;
	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	auto streamProps = getStreamIoProps(F, GeneratedAllocas);
	for (StreamChannelProps &s : streamProps) {
		if (s.isOutput)
			continue;
		changed = true;
		StreamIoDetector cfg(s.dataWidth,
				reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(s.ios));
		cfg.detectIoAccessGraphs(F.getEntryBlock());
		cfg.resolvePossibleOffset();
		IRBuilder<> builder(F.getEntryBlock().getFirstNonPHI());
		s.createCommonVars(builder);
		StreamReadRewriter srr(cfg, s, &DTU, nullptr);
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
