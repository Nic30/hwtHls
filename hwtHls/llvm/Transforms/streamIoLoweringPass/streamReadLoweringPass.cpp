#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPass.h>
#include <algorithm>
#include <sstream>

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/TargetFolder.h>
#include <llvm/Analysis/LoopInfo.h>

#include <hwtHls/llvm/bitMath.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoCfgDetector.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamReadLoweringPassPriv.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/streamIoRewriter.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

// #include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

using namespace llvm;

namespace hwtHls {

class StreamReadChunk {
public:
	const StreamChannelProps &streamProps;
	const std::vector<size_t> &possibleOffsets;
	std::pair<size_t, size_t> wordCntRange;
	StreamReadBehaviorType readBehavior;
	size_t chunkWidth;
	StreamIoDetector::HlsReadOrWrite *read;
	SmallVector<StreamChannelWordValue> inWords;
	// The format of prevWordVars is expected to be following.
	// The words which are read optionally are placed on the begin of
	// prevWordVars, the remaining items are are always read.
	// This ordering is use to have optional reads only on the beginning.
	// :note: lastWord is optionally loaded based on offset
	// :note: preLastWord is a backup of current word before lastWord is loaded
	//
	// Variant 0(PWF_STATIC): in this case the chunk is always aligned to start of the word
	//    word[0]
	//    word[1]
	//    ...
	//
	// Variant 1 (PWF_LEFTOVER_STATIC):
	//    * The chunk have same number of words for every alignment but some offset >0
	//      and thus previous stream word is sometimes required.
	//    word[-1] lastWord
	//    word[0]
	//    word[1]
	//    ...
	//
	// Variant 2 (PWF_LEFTOVER_OPTIONAL_STATIC):
	//   There is offset=0 which does not require leftover word and some offset which end overlaps to next
	//   next word at end.
	//   word[-2] preLastWord (leftover)
	//   word[-1] lastWord (optional input word read to cover for offsets which require 1 more word
	//                      due to end overflow set to leftover if not loaded)
	//   word[0]
	//   word[1]
	//   ...
	//  :see: :meth:`~.getNumOfSkippedWordsForOffset`
	enum PartialWordsFormat {
		// :note: static words are newly loaded for every offset
		// :note: leftover word is there if some offset != 0 and thus data from previous word have to be used
		// :note: optional word is loaded because end of chunk reaches next word
		//        and there is some offset which does not reach it
		PWF_STATIC,
		PWF_LEFTOVER_STATIC,
		PWF_LEFTOVER_OPTIONAL_STATIC,
	};
	PartialWordsFormat partialWordFormat;

	StreamReadChunk(const StreamChannelProps &streamProps,
			const std::vector<size_t> &possibleOffsets, size_t chunkWidth,
			StreamIoDetector::HlsReadOrWrite *read) :
			streamProps(streamProps), //
			possibleOffsets(possibleOffsets), //
			wordCntRange(
					streamProps._resolveMinMaxSegmentCount(possibleOffsets,
							chunkWidth)), //
			readBehavior(streamReadGetBehavior(read)), //
			chunkWidth(chunkWidth) //
					, read(read) {
		partialWordFormat = PWF_STATIC;
		if (mayReadLeftoverData()) {
			if (mayConsume1MoreWordDueToOffset()
					|| (possibleOffsets[0] == 0
							&& all_of(possibleOffsets,
									[&streamProps, chunkWidth](size_t off) {
										return off + chunkWidth
												<= streamProps.dataWidth;
									}))) {
				// consumes extra word for some offset or
				// always fits into 1 word but it may be leftover or newly loaded word
				partialWordFormat = PWF_LEFTOVER_OPTIONAL_STATIC;
			} else {
				partialWordFormat = PWF_LEFTOVER_STATIC;
			}
		} else {
			assert(!mayConsume1MoreWordDueToOffset());
		}

	}
	bool isReliable() const {
		return readBehavior == StreamReadBehaviorType::RELIABLE;
	}
	bool mayReadLeftoverData() const {
		// first word may be read of leftover word (and may also be read of new bus word)
		return possibleOffsets.size() > 1 || possibleOffsets[0] != 0;
	}
	bool mustReadLeftoverData() const {
		// first word is always read of leftover word
		return possibleOffsets[0] != 0;
	}
	bool readsLeftoverDataWithOffset(size_t off) const {
		return off != 0;
	}
	bool mayConsume1MoreWordDueToOffset() const {
		return wordCntRange.first != wordCntRange.second;
	}
	size_t getNumOfSkippedWordsForOffset(size_t off) const {
		switch (partialWordFormat) {
		case PartialWordsFormat::PWF_STATIC:
			return 0;
		case PartialWordsFormat::PWF_LEFTOVER_STATIC: {
			if (readsLeftoverDataWithOffset(off))
				return 0;
			else
				return 1;
		}

		case PartialWordsFormat::PWF_LEFTOVER_OPTIONAL_STATIC: {
			size_t wCnt = streamProps._getBusWordCntForChunk(off, chunkWidth);
			if (readsLeftoverDataWithOffset(off)) {
				if (wCnt == wordCntRange.first) {
					//  example read 5B from 3B IO with offset=1B
					//  |   | 0 | 1 | // leftover
					//  |   | 0 | 1 | // optional word containing leftover because it was not loaded
					//  | 2 | 3 | 4 | // 1st static word
					// optional word is unused, and occupied by leftover
					return 1;
				} else if (wCnt == wordCntRange.second) {
					//  example read 5B from 3B IO with offset=2B
					//  |   |   | 0 | // leftover
					//  | 1 | 2 | 3 | // optional word containing newly loaded data
					//  | 4 |   |   | // 1st static word
					return 0;
				} else {
					llvm_unreachable(
							"wordCntRange or wCnt computed incorrectly");
				}
			} else {
				if (wCnt == wordCntRange.first) {
					//  example read 5B from 3B IO with offset=0B
					//  |   |   |   | // leftover
					//  | 0 | 1 | 2 | // optional word containing newly loaded data
					//  | 3 | 4 |   | // 1st static word
					//  skip the leftover word
					return 1;
				} else {
					llvm_unreachable(
							"wordCntRange or wCnt computed incorrectly");
				}
			}
		}
		};
		llvm_unreachable(
				"StreamReadChunk::getNumOfSkippedWordsForOffset: every case should be covered");
		//if (mayReadLeftoverData() && !readsLeftoverDataWithOffset(off))
		//	++skipped;
		//if (mayConsume1MoreWordDueToOffset()) {
		//	if (streamProps._getBusWordCntForChunk(off, chunkWidth)
		//			== wordCntRange.first) {
		//		++skipped;
		//	} else if (mayReadLeftoverData()
		//			&& readsLeftoverDataWithOffset(off)) {
		//		// skip read of optional word at the beginning because leftover word is used
		//		// instead of it
		//		++skipped;
		//	}
		//
		//}
		//else if (possibleOffsets.back() + chunkWidth <= streamProps.dataWidth
		//		&& mayReadLeftoverData() && readsLeftoverDataWithOffset(off)
		//		&& !mustReadLeftoverData()) {
		//	// the chunk may occupy only leftover word or 1 new word
		//	++skipped;
		//}
		//assert(skipped <= 2);
		//return skipped;

		//size_t skippedCnt = 0;
		//// :note: mayResultInDiffentNoOfWords means we have variant 1 or 2.
		//if (possibleOffsets.size() != 1) {
		//	if (*off == 0) {
		//		// (Variant 1, 2)
		//		// now not reading last word loaded for predecessor but other offsets variant are using it
		//		++chunkWordIt;
		//		++skippedCnt;
		//	}
		//}
		//bool canConsummeLeftoverFromPrevWord = possibleOffsets.size() != 1
		//		&& possibleOffsets[0] == 0 && *off != 0;
		//bool itIsPossibleThat1MoreWordWillBeConsummedForDifferentOffset =
		//		(wordCntRange.first != wordCntRange.second
		//				|| canConsummeLeftoverFromPrevWord);
		//if (itIsPossibleThat1MoreWordWillBeConsummedForDifferentOffset
		//		&& streamProps._getBusWordCntForChunk(*off, chunkWidth)
		//				== wordCntRange.first) {
		//	// (Variant 2)
		//	// some other offset is so large that there is 1 additional word on end required
		//	// but it is not this offset, so we read word less
		//	++chunkWordIt;
		//	++skippedCnt;
		//}
		//// errs() << "prevWordVars for " << *read << "  " << *off << "\n";
		//// for (auto &x : prevWordVars) {
		//// 	errs() << *x.data << "\n";
		//// }

	}
};

class StreamReadRewriter: public StreamIoRewriter {
public:
	using StreamIoRewriter::StreamIoRewriter;
protected:
	bool _mayLoadDisabledSegment(StreamIoDetector::HlsReadOrWrite *read) const;
	void _createLoopForEmptySegmentSkip(LoadInst *ld);
	void _rewriteAdtAccessToWordAccessInstruction(
			StreamIoDetector::HlsReadOrWrite *read) override;
	// create loads from IO which will always happen for every combination of offset
	void _prepareStaticPrevWordVars(StreamReadChunk &readInfo,
			size_t staticWordCnt, bool skipDisabledSegments);
	void _consumeReadWordsAndCreateResultData(StreamReadChunk &readInfo);
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
	assert(possibleOffsets.size());
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
			streamProps.ioArg, /*isVolatile*/true, read->getName() + ".optLd");
	if (_mayLoadDisabledSegment(read)) {
		_createLoopForEmptySegmentSkip(ioWordLd);
	}
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

void StreamReadRewriter::_prepareStaticPrevWordVars(StreamReadChunk &readInfo,
		size_t staticWordCnt, bool skipDisabledSegments) {
	assert(staticWordCnt);
	assert(
			staticWordCnt <= (1ul << 32)
					&& "sanity check that the staticWordCnt did not overflow");
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
			(readInfo.wordCntRange.first == readInfo.wordCntRange.second
					|| readInfo.wordCntRange.first + 1
							== readInfo.wordCntRange.second)
					&& "max and min number of words for this chunk can be only (chunkWidth//dataWidth)(+1)");
	//auto setMaskOrEmptyToFullValid = [](StreamChannelWordValue &w) {
	//	if (w.empty)
	//		w.empty = ConstantInt::get(w.empty->getType(), 0);
	//	if (w.mask)
	//		w.mask = ConstantInt::getAllOnesValue(w.mask->getType());
	//};
	//if (readInfo.isReliable()) {
	//	for (auto &w : readInfo.inWords) {
	//		setMaskOrEmptyToFullValid(w);
	//	}
	//}

	auto BB = readInfo.read->getParent();
	SmallVector<BasicBlock*> eofCheckingBlocks;
	// :note: if this is the case which can read +1 words the load is already prepared before
	//     call of this function and is stored in streamProps tmp variables
	for (size_t i = 0; i < staticWordCnt; ++i) {
		// load next word from IO
		if (!readInfo.isReliable() && readInfo.inWords.size()
				&& (i > 1
						|| readInfo.partialWordFormat
								!= StreamReadChunk::PartialWordsFormat::PWF_STATIC)) {
			// construct if-then for next read only if previous did not end with eof
			// :note: original read instruction will be after this new if-then
			eofCheckingBlocks.push_back(BB);
			auto prevEoF = readInfo.inWords.back().eof;
			assert(prevEoF);
			Instruction *thenBlockTerm = llvm::SplitBlockAndInsertIfElse(
					prevEoF, readInfo.read, false, /*BranchWeights*/nullptr,
					DTU, LI);
			BB = readInfo.read->getParent();
			assert(BB == thenBlockTerm->getSuccessor(0));
			Builder.SetInsertPoint(thenBlockTerm);
		}
		auto *ioWordLd = Builder.CreateLoad(streamProps.segmentTy,
				streamProps.ioArg, /*isVolatile*/true,
				readInfo.read->getName() + ".r" + std::to_string(i));
		if (i == 0 && skipDisabledSegments) {
			_createLoopForEmptySegmentSkip(ioWordLd);
		}
		StreamChannelWordValue w = StreamChannelWordValue::parseNativeWord(streamProps, Builder,
				ioWordLd);
		readInfo.inWords.push_back(w);
		if (!readInfo.isReliable()) {
			streamProps.setAllData(Builder, readInfo.inWords.back());
		}
	}
	if (readInfo.isReliable()) {
		// store remainder of loaded word if required for later use of next read
		streamProps.setAllData(Builder, readInfo.inWords.back());
	} else {
		if (eofCheckingBlocks.size()) {
			// the values in readInfo.inWords are localized in sequence of if-then, we have to create
			// phis to select PoisonValue if if-then was not performed
			// BB0 ->  BB1 -> BB2 -------+
			//  |       |      |         |
			// eof0    eof1   eof2       v
			//  +-------+------+------> BB with original read
			auto inWordBegin = readInfo.inWords.begin()
					+ readInfo.inWords.size() - eofCheckingBlocks.size();
			SmallVector<StreamChannelWordValue> loadedWords;
			loadedWords.insert(loadedWords.end(), inWordBegin,
					readInfo.inWords.end());
			assert(loadedWords.size() == staticWordCnt);
			auto &exitBB = *BB;
			Builder.SetInsertPoint(exitBB.begin());
			for (auto &w : make_range(inWordBegin, readInfo.inWords.end())) {
				// for each out word construct phis for every member of StreamChannelWordValue
				// the value will be PoisonValue/0 if value have not been yet read
				auto wAsArray = w.asArray();
				for (auto &v : wAsArray)
					if (v) {
						auto _v = v;
						v = Builder.CreatePHI(_v->getType(), staticWordCnt);
						v->takeName(_v);
					}
				w.setFromArray(wAsArray);
			}
			// :note: items in readInfo.inWords now using phis, original values are backuped in loadedWords
			auto addPhiIncomingUnused = [](StreamChannelWordValue &w,
					BasicBlock *newPredBB) {
				// sof/eof/enable/error are or-ed (using 0 as default)
				// data/mask is concatenated (using PoisonValue for data, 0 for mask as default)
				// empty is summed (using wordbytecnt as default)
				for (auto v : w.asArray()) {
					if (!v)
						continue;
					auto phi = dyn_cast<PHINode>(v);
					assert(phi);
					Value *incVal;
					if (v == w.data) {
						incVal = PoisonValue::get(phi->getType());
					} else if (v == w.empty) {
						incVal = ConstantInt::get(phi->getType(),
								w.props.dataWidth / w.props.byteWidth);
					} else {
						incVal = ConstantInt::get(phi->getType(), 0);
					}
					phi->addIncoming(incVal, newPredBB);
				}
			};
			auto addPhiIncomingSelf = [](StreamChannelWordValue &wPhi,
					StreamChannelWordValue &wIn, BasicBlock *newPredBB) {
				for (const auto& [vPhi, vOriginal] : zip(wPhi.asArray(),
						wIn.asArray())) {
					if (!vPhi)
						continue;
					auto phi = dyn_cast<PHINode>(vPhi);
					assert(phi);
					phi->addIncoming(vOriginal, newPredBB);
				}
			};
			size_t bbIndex = 0;
			for (auto *eofCheckingBB : eofCheckingBlocks) {
				bool isLastBB = eofCheckingBB == eofCheckingBlocks.back();
				auto *thenBB = eofCheckingBB->getTerminator()->getSuccessor(1);
				size_t wordIndex = 0;
				// add Incoming value for every phi for every word
				for (const auto& [wPhi, wIn] : zip(
						make_range(inWordBegin, readInfo.inWords.end()),
						loadedWords)) {
					// in BB0 word 0 is undefined because it is read in then block after BB0
					if (wordIndex < bbIndex) {
						addPhiIncomingSelf(wPhi, wIn, eofCheckingBB);
					} else {
						addPhiIncomingUnused(wPhi, eofCheckingBB);
					}
					if (isLastBB) {
						addPhiIncomingSelf(wPhi, wIn, thenBB);
					}
					wordIndex++;
				}
				++bbIndex;
			}
		}
	}
}

void StreamReadRewriter::_consumeReadWordsAndCreateResultData(
		StreamReadChunk &readInfo) {
	Builder.SetInsertPoint(readInfo.read);
	llvm::SmallVector<StreamChannelWordValue> &prevWordVars = readInfo.inWords;
	auto *readResVar = Builder.CreateAlloca(readInfo.read->getType(), nullptr,
			readInfo.read->getName() + ".r");
	//readResVar->takeName(readInfo.read);
	streamProps.GeneratedAllocas.push_back(readResVar);
	std::vector<llvm::BasicBlock*> offsetBranches =
			_createBranchForEachOffsetVariant(readInfo.possibleOffsets);

	auto off = readInfo.possibleOffsets.begin();
	for (BasicBlock *br : offsetBranches) {
		if (br == readInfo.read->getParent()) {
			Builder.SetInsertPoint(readInfo.read);
		} else {
			Builder.SetInsertPoint(br,
					llvm::BasicBlock::iterator(&br->front()));
		}
		const auto DATA_WIDTH = streamProps.dataWidth;
		size_t end = *off + readInfo.chunkWidth;
		size_t inWordOffset = *off % DATA_WIDTH;
		size_t _w = readInfo.chunkWidth;
		size_t wordCnt = div_ceil(end == 0 ? 0 : end - 1, DATA_WIDTH);
		// errs() << "off, chunkWidth: " << *off << " " << readInfo.chunkWidth;
		// resolve first word (chunkWords) used for this offset variant
		size_t skippedCnt = readInfo.getNumOfSkippedWordsForOffset(*off);
		auto chunkWordsEnd = prevWordVars.end();

		//errs() << "  skippedCnt: " << skippedCnt << "  " << *readInfo.read
		//		<< "\n";
		assert(prevWordVars.size() == wordCnt + skippedCnt);

		// vector of parts to build replacement for value of this original ADT read
		llvm::SmallVector<StreamChannelWordValue> parts;
		for (auto chunkWordIt = prevWordVars.begin() + skippedCnt;
				chunkWordIt != chunkWordsEnd; ++chunkWordIt) {
			assert(inWordOffset < DATA_WIDTH);
			size_t bitsToTake = std::min(_w, DATA_WIDTH - inWordOffset);
			auto partRead = *chunkWordIt;
			bool isLast = chunkWordIt == (chunkWordsEnd - 1);
			bool isGuaranteedToBeNotEoF = readInfo.isReliable() && !isLast;
			bool isGuarangeedToContainSomeData = readInfo.isReliable();
			if (inWordOffset == 0) {
				// read a new word
				if (bitsToTake != DATA_WIDTH) {
					//assert bitsToTake > 0, bitsToTake
					partRead = partRead.slice(Builder, inWordOffset, bitsToTake,
							isGuaranteedToBeNotEoF,
							isGuarangeedToContainSomeData);
				} else {
					// take whole word as is
					if (readInfo.isReliable()) {
						// delete byte enable encoding as we assume all bytes are valid because this is reliable read
						partRead.props = partRead.props.resize(
								partRead.props.dataWidth, { },
								ByteEnableEncoding::BEE_NONE);
						partRead.empty = nullptr;
						partRead.mask = nullptr;
					}
				}
			} else {
				// take from previous word
				partRead = partRead.slice(Builder, *off, bitsToTake,
						isGuaranteedToBeNotEoF, isGuarangeedToContainSomeData);
				inWordOffset = 0;
			}
			//if (readInfo.isReliable()) {
			//	switch (streamProps.byteEnableEncoding) {
			//	case ByteEnableEncoding::BEE_NONE:
			//		break;
			//	case ByteEnableEncoding::BEE_MASK:
			//		partRead.mask = nullptr;
			//		break;
			//	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY:
			//		partRead.empty = nullptr;
			//		break;
			//	default:
			//		llvm_unreachable("invalid ByteEnableEncoding value");
			//	}
			//}
			_w -= bitsToTake;
			parts.push_back(partRead);
		}
		llvm::Value *isFollowedByMoreValidDataInLastWord = nullptr;
		size_t newOffset = end % DATA_WIDTH;
		if (newOffset != 0) {
			switch (streamProps.byteEnableEncoding) {
			case ByteEnableEncoding::BEE_NONE:
				break;
			case ByteEnableEncoding::BEE_MASK: {
				if (streamProps.hasMask()) {
					auto maskOfLastWord = (chunkWordsEnd - 1)->mask;
					isFollowedByMoreValidDataInLastWord =
							CreateBitRangeGetConst(&Builder, maskOfLastWord,
									newOffset / 8, 1);
				}
				break;
			}
			case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
				if (streamProps.hasEmpty()) {
					auto emptyOfLastWord = (chunkWordsEnd - 1)->empty;
					// size is larger than end of this section (newOffset)
					// = empty < bytesInWord - size
					size_t bytesInWord = streamProps.dataWidth
							/ streamProps.byteWidth;
					isFollowedByMoreValidDataInLastWord = Builder.CreateICmpULT(
							emptyOfLastWord,
							ConstantInt::get(emptyOfLastWord->getType(),
									bytesInWord - newOffset));
				}
				break;
			}
			default:
				llvm_unreachable("invalid ByteEnableEncoding value");
			}
		}
		auto _readRes = StreamChannelWordValue::concat(Builder, parts,
				readInfo.isReliable());
		if (readInfo.isReliable()) {
			switch (streamProps.byteEnableEncoding) {
			case ByteEnableEncoding::BEE_NONE:
				break;
			case ByteEnableEncoding::BEE_MASK: {
				for (auto &p : parts) {
					assert(!p.mask);
				}
				assert(!_readRes.mask);
				break;
			}
			case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
				for (auto &p : parts) {
					assert(!p.empty);
				}
				assert(!_readRes.empty);
				break;
			}
			default:
				llvm_unreachable("invalid ByteEnableEncoding value");
			}
		}
		//_readRes.populateWithDummyMaskOrEmptyIfNecessary(streamProps);

		llvm::Value *readRes = _readRes.flatten(Builder,
				isFollowedByMoreValidDataInLastWord);
		assert(
				readRes->getType()->getIntegerBitWidth()
						== readInfo.read->getType()->getIntegerBitWidth());
		if (!readRes->getName().contains(readInfo.read->getName())) {
			readRes->setName(
					readRes->getName() + "(" + readInfo.read->getName() + ")");
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
	assert(readInfo.read->getParent() != nullptr);
	//if (sequelBlock == read->getParent()) {
	// original read should always end up in sequel block because everything we generated should be before it
	Builder.SetInsertPoint(readInfo.read);
	//} else {
	//	errs() << "builder.SetInsertPoint(sequelBlock\n";
	//	builder.SetInsertPoint(sequelBlock,
	//			BasicBlock::iterator(&sequelBlock->front()));
	//}
	// the insertion point should be the place behind all newly generated instructions which are implementing
	// original stream read pseudo-instruction
	auto *readRes = Builder.CreateLoad(readInfo.read->getType(), readResVar);
	readRes->takeName(readInfo.read);
	readInfo.read->replaceAllUsesWith(readRes);
}

//bool StreamReadRewriter::_canFitOnlytToFirstWord() {
//
//}
//
bool StreamReadRewriter::_mayLoadDisabledSegment(
		StreamIoDetector::HlsReadOrWrite *read) const {
	return streamProps.segmentCnt > 1 && cfg.isDirectlyAfterSoF(read);
}

void StreamReadRewriter::_createLoopForEmptySegmentSkip(LoadInst *ld) {
	// create loop which will skip empty segments
	BasicBlock *BB = ld->getParent();
	if (BB->size() != 2 || !BB->getSinglePredecessor()
			|| !BB->getSingleSuccessor()) {
		splitBlockBefore(BB, ld, DTU, LI, nullptr,
				BB->getName() + ".segmentEnCheckBefore");
		assert(BB == ld->getParent());
	}
	if (BB->size() != 2 || !BB->getSinglePredecessor()
			|| !BB->getSingleSuccessor()) {
		SplitBlock(BB, ld->getNextNode(), DTU, LI, nullptr,
				BB->getName() + ".segmentEnCheckAfter");
		BB = ld->getParent();
	}

	auto curTerm = BB->getTerminator();
	auto suc = BB->getSingleSuccessor();
	assert(suc);
	curTerm->eraseFromParent();
	Builder.SetInsertPoint(BB); // after read
	assert(streamProps.hasEnable());
	auto enable = CreateBitRangeGetConst(&Builder, ld,
			streamProps.getOffsetOfEnable(), 1, ld->getName() + ".enable");
	BranchInst::Create(suc, BB, enable, BB); // loop while enable=0 (offset is not changing)
	if (DTU) {
		DTU->applyUpdates( { { DominatorTree::Insert, BB, BB }, });
	}
	if (LI) {
		auto *ParentL = LI->getLoopFor(BB);
		Loop *WhileNotEnableL = LI->AllocateLoop();
		if (ParentL)
			ParentL->addChildLoop(WhileNotEnableL);
		else
			LI->addTopLevelLoop(WhileNotEnableL);
		LI->changeLoopFor(BB, WhileNotEnableL);
	}
	Builder.SetInsertPoint(suc->begin());
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
							<< "[todo] Use first word mask to resolve the offsetVar, possibleOffsets: [";
					for (size_t off : possibleOffsets) {
						ss << off << ", ";
					}
					ss << "]";

					// read words to satisfy initial offset
					throw std::runtime_error(ss.str());
				}
			} else {
				Builder.SetInsertPoint(read);
				streamProps.commonVarsInitialize(Builder);
				streamProps.setOffsetVar(Builder, possibleOffsets[0]);
			}
		}
	} else {
		Builder.SetInsertPoint(read);
		if (possibleOffsets.size()) {
			// if number of words differs in offset variants we need to insert a new block which is entered conditionally for specific offset values
			// :note: the information about which word is last is stored in offset variable and does not need to be explicitly specified

			size_t chunkWidth = streamReadGetOrigChunkBitWidth(read);
			// shared words for offset variants
			StreamReadChunk readInfo(streamProps, possibleOffsets, chunkWidth,
					read);
			size_t staticWordCnt;
			switch (readInfo.partialWordFormat) {
			case StreamReadChunk::PartialWordsFormat::PWF_STATIC:
				staticWordCnt = readInfo.wordCntRange.first;
				break;
			case StreamReadChunk::PartialWordsFormat::PWF_LEFTOVER_STATIC: {
				auto leftoverWord = streamProps.getAllData(Builder);
				readInfo.inWords.push_back(leftoverWord);
				staticWordCnt = readInfo.wordCntRange.first - 1;
				break;
			}
			case StreamReadChunk::PartialWordsFormat::PWF_LEFTOVER_OPTIONAL_STATIC: {
				auto leftoverWord = streamProps.getAllData(Builder);
				readInfo.inWords.push_back(leftoverWord);
				_handleOptionalReadsDependingOnCurrentOffset(possibleOffsets,
						readInfo.wordCntRange, chunkWidth, read);
				auto optionalWord = streamProps.getAllData(Builder);
				readInfo.inWords.push_back(optionalWord);
				if (readInfo.wordCntRange.second == 1)
					staticWordCnt = 0; // case where chunk always fits into 1 word and this word can be leftover or not
				else {
					assert(readInfo.wordCntRange.second >= 2);
					staticWordCnt = readInfo.wordCntRange.second - 2;
				}
				break;
			}
			}
			if (staticWordCnt)
				_prepareStaticPrevWordVars(readInfo, staticWordCnt, _mayLoadDisabledSegment(read));

			// * collect/construct all reads common for every successor branch
			// * replace original read of ADT with a result composed of word reads
			_consumeReadWordsAndCreateResultData(readInfo);
		} else {
			// the read is unreachable
			read->replaceAllUsesWith(PoisonValue::get(read->getType()));
		}
	}
}

llvm::PreservedAnalyses StreamReadLoweringPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &FAM) {
	//if (verifyModule(*F.getParent(), &errs())) {
	//	assert(false && "corrupted at input");
	//}
	auto *AC = FAM.getCachedResult<AssumptionAnalysis>(F);
	LazyValueInfo *LVI = nullptr;
	auto &DT = FAM.getResult<DominatorTreeAnalysis>(F);
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Eager);
	bool changed = false;
	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	auto streamProps = getStreamIoProps(F, GeneratedAllocas);
	auto &DL = F.getDataLayout();

	// :note: copied from llvm-18 combineInstructionsOverFunction
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
		if (s.dataOffsetVar && !LVI)
			LVI = &FAM.getResult<LazyValueAnalysis>(F);
		StreamIoDetector cfg(LVI, s.dataWidth, s.dataOffsetVar,
				reinterpret_cast<llvm::SetVector<const llvm::CallInst*>&>(s.ios));
		cfg.detectIoAccessGraphs(F.getEntryBlock());
		cfg.resolvePossibleOffset();
		//cfg.dump();
		//if (LVI)
		//	LVI->clear();

		Builder.SetInsertPoint(F.getEntryBlock().getFirstNonPHIIt());
		s.createCommonVars(Builder);
		StreamReadRewriter srr(cfg, s, Builder, &DTU, nullptr);
		srr.rewriteAdtAccessToWordAccess(F.getEntryBlock());

		DTU.flush();
	}
	if (changed) {
#ifndef NDEBUG
		// errs() << "StreamReadLoweringPass.afer:\n" << F << "\n";
		std::string errTmp =
				"hwtHls::StreamReadLoweringPass corrupted function ";
		llvm::raw_string_ostream errSS(errTmp);
		errSS << F.getName().str();
		errSS << "\n";
		if (verifyModule(*F.getParent(), &errSS)) {
			throw std::runtime_error(errSS.str());
		}
		// writeCFGToDotFile(F, "tmp/StreamReadLoweringPass.after.no-reg2mem.dot",
		// 		FAM);
		assert(DT.verify());
#endif
		finalizeStreamIoLowerig(F, FAM, DT, streamProps, false,
				GeneratedAllocas);
		llvm::PreservedAnalyses PA;
		return PA;
	} else {
		return llvm::PreservedAnalyses::all();
	}
}

}
