#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentStreamReadUntilEoF.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/StreamChannelWordValue.h>

using namespace llvm;

namespace hwtHls {

StreamReadUntilEoFCFGFragment::StreamReadUntilEoFCFGFragment() :
		ioPtr(nullptr), exit(nullptr) {
}

CallInst* StreamReadUntilEoFCFGFragment::mergeReads(
		llvm::IRBuilderBase &Builder, //llvm::DomTreeUpdater &DTU,
		const StreamChannelFormatInfo &streamProps,
		const llvm::SmallVector<llvm::CallInst*> &reads) {
	assert(reads.size() > 1);
	//{
	//	// update cfg in the case that some blocks with read have more predecessors
	//	// (to start at the first block where the merged read will be constructed)
	//	SmallVector<llvm::DominatorTree::UpdateType> DTUpdates;
	//	BasicBlock *topBB = reads[0]->getParent();
	//	BasicBlock *prevBB = nullptr;
	//	bool topBBCheckedToBeginWithRead = false;
	//	for (auto r : reads) {
	//		auto BB = r->getParent();
	//		if (prevBB) {
	//			auto prev = BB->getUniquePredecessor();
	//			if (prev) {
	//				assert(prev == prevBB);
	//			} else {
	//				assert(&*BB->begin() == r);
	//				if (!topBBCheckedToBeginWithRead) {
	//					assert(&*topBB->begin() == reads[0]);
	//					assert(topBB->phis().empty());
	//					topBBCheckedToBeginWithRead = true;
	//				}
	//				assert(BB->phis().empty());
	//				SmallVector<BasicBlock*> preds(predecessors(BB));
	//				for (auto pred : preds) {
	//					if (pred != prevBB) {
	//						pred->getTerminator()->replaceSuccessorWith(BB,
	//								topBB);
	//						DTUpdates.push_back( { DominatorTree::Delete, pred,
	//								BB });
	//						DTUpdates.push_back( { DominatorTree::Insert, pred,
	//								topBB });
	//					}
	//				}
	//			}
	//		}
	//		prevBB = BB;
	//	}
	//}

	auto *srcIO = streamReadGetIoArg(reads[0]);

	size_t mergedDataBitWidth = 0;
	bool mergedReadIsReliable = true;
	size_t reliableReadsCntInMerged = 0;
	bool unrealiabeReadSeen = false;
	for (auto r : reads) {
		mergedDataBitWidth += streamReadGetOrigChunkBitWidth(r);
		//mergedReadIsReliable && reads[0]->getParent() == r->getParent() &&
		if (!unrealiabeReadSeen
				&& streamReadGetBehavior(r)
						== StreamReadBehaviorType::RELIABLE) {
			// the merged read is reliable only if all reads were reliable and all are in the same block
			// (if they were not in same block they are conditionally executed thus data may not be present)
			if (reads[0]->getParent() != r->getParent())
				mergedReadIsReliable = false; // we need byte enable to implement jumps if data not valid
		} else {
			mergedReadIsReliable = false;
			unrealiabeReadSeen = true;
		}
		if (mergedReadIsReliable)
			reliableReadsCntInMerged++;
	}

	assert(mergedDataBitWidth % 8 == 0);
	Builder.SetInsertPoint(reads[0]);
	std::optional<hwtHls::ByteEnableEncoding> byteEnableEncodingOverride;
	if (mergedReadIsReliable)
		byteEnableEncodingOverride = ByteEnableEncoding::BEE_NONE;
	auto streamPropsForMerged = streamProps.resize(mergedDataBitWidth,
			streamProps.supportZLP || !mergedReadIsReliable,
			byteEnableEncodingOverride);
	size_t returnBitWidth =
			streamPropsForMerged.segmentTy->getIntegerBitWidth();

	auto mergedRead = CreateStreamRead(&Builder, srcIO, mergedDataBitWidth,
			returnBitWidth, mergedReadIsReliable);
	streamPropsForMerged.CreateAssumptionForControl(Builder, mergedRead);
	auto mergedReadWord = StreamChannelWordValue::parseNativeWord(
			streamPropsForMerged, Builder, mergedRead);

	size_t dataBitOffset = 0;
	size_t readIndex = 0;
	for (auto *r : reads) {
		auto dataWidth = streamReadGetOrigChunkBitWidth(r);
		//Builder.SetInsertPoint(r);
		bool rIsLast = reads.back() == r;
		bool rDataAlwaysPresent = readIndex < reliableReadsCntInMerged;
		bool nextRDataAlwaysPresent = reliableReadsCntInMerged
				&& readIndex + 1 < reliableReadsCntInMerged;
		auto partWordForR = mergedReadWord.slice(Builder, dataBitOffset,
				dataWidth,                                                 //
				/*isGuaranteedToBeNotEoF*/!rIsLast && nextRDataAlwaysPresent, //
				/*isGuarangeedToContainSomeData*/rDataAlwaysPresent       //
				);
		partWordForR.populateWithDummyMaskOrEmptyIfNecessary(Builder);
		if (streamReadGetBehavior(r)
				== StreamReadBehaviorType::RELIABLE) {
			partWordForR.stripByteEnableEncoding();
		}
		auto newR = partWordForR.flatten(Builder, nullptr);
		assert(newR->getType() == r->getType());
		newR->takeName(r);
		r->replaceAllUsesWith(newR);

		dataBitOffset += dataWidth;
		++readIndex;
	}
	BasicBlock *topBB = reads[0]->getParent();
	BasicBlock *prevBB = nullptr;
	bool topBBCheckedToBeginWithRead = false;
	bool allInSameBB = all_of(reads, [topBB](CallInst *CI) {
		return CI->getParent() == topBB;
	});
	for (auto *r : reads) {
		auto BB = r->getParent();
		if (prevBB) {
			auto prev = BB->getUniquePredecessor();
			if (prev) {
				assert(prev == prevBB);
			} else {
				if (!allInSameBB) {
					assert(&*BB->begin() == r);
					if (!topBBCheckedToBeginWithRead) {
						assert(&*topBB->begin() == reads[0]);
						topBBCheckedToBeginWithRead = true;
					}
				}
			}
		}
		prevBB = BB;
		r->eraseFromParent();
	}
	return mergedRead;
}

std::optional<StreamReadUntilEoFCFGFragment> StreamReadUntilEoFCFGFragment::detect(
		IRBuilderBase &Builder, BasicBlock &BlockWithRead,
		llvm::SmallPtrSetImpl<const llvm::BasicBlock*> &LoopHeaders) {
	StreamReadUntilEoFCFGFragment res;
	auto *BB = &BlockWithRead;
	llvm::SmallSet<BasicBlock*, 16> seen;

	for (;;) {
		if (seen.contains(BB)) {
			break;
		} else {
			seen.insert(BB);
		}
		if (!res.reads.empty() && LoopHeaders.contains(BB))
			break; // can not merge reads in some loop with reads before loop

		// [todo] check that the first block dominates all others
		for (auto &I : *BB) {
			if (auto *CI = dyn_cast<CallInst>(&I)) {
				if (IsStreamRead(CI)
						&& (!res.ioPtr || streamReadGetIoArg(CI) == res.ioPtr)) {
					if (!res.ioPtr) {
						res.ioPtr = streamReadGetIoArg(CI);
					}
					SmallVector<CallInst*> readsToMerge;
					readsToMerge.push_back(CI);
					for (Instruction &I2 : make_range(
							I.getNextNode()->getIterator(), BB->end())) {
						if (auto *CI2 = dyn_cast<CallInst>(&I2)) {
							if (IsStreamRead(CI2)
									&& streamReadGetIoArg(CI2) == res.ioPtr) {
								readsToMerge.push_back(CI2);
							}
						}
					}
					if (readsToMerge.size() == 1) {
						// no other reads in this block
					} else {
						// merge all reads in this block into first one
						if (!res.streamProps.has_value()) {
							assert(isa<Argument>(res.ioPtr));
							res.streamProps =
									StreamChannelFormatInfo::findInMetadata(
											*cast<Argument>(res.ioPtr));
						}
						CI = mergeReads(Builder, res.streamProps.value(),
								readsToMerge);
						assert(CI);
					}
					res.reads.push_back(CI);
					break;
				}
			}
		}
		if (!res.reads.empty() && !res.streamProps.has_value()) {
			assert(isa<Argument>(res.ioPtr));
			res.streamProps = StreamChannelFormatInfo::findInMetadata(
					*cast<Argument>(res.ioPtr));
		}
		auto Term = dyn_cast<BranchInst>(BB->getTerminator());
		if (res.reads.empty() || !Term || !Term->isConditional()
				|| !res.streamProps.value().isStreamReadEoF(res.reads.back(),
						Term->getCondition())) {
			break;
		} else {
			if (res.exit) {
				if (res.exit != Term->getSuccessor(0))
					if (res.reads.size() < 2)
						return {};
			} else {
				res.exit = Term->getSuccessor(0);
			}
			BB = Term->getSuccessor(1);
		}

	}
	// exit is verified to be present, res.reads which are in sequence of blocks which are juped if to each other if not last

	if (res.reads.size() < 2)
		return {};

	return res;
}
}
