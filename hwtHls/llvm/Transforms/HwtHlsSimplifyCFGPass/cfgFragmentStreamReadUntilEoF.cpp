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
		llvm::IRBuilderBase &Builder,
		const StreamChannelFormatInfo &streamProps,
		const llvm::SmallVector<llvm::CallInst*> &reads) {
	assert(reads.size() > 1);

	size_t mergedDataBitWidth = 0;
	bool mergedReadIsReliable = true;
	size_t reliableReadsCnt = 0;
	for (auto r : reads) {
		mergedDataBitWidth += streamReadGetOrigChunkBitWidth(r);
		if (mergedReadIsReliable && reads[0]->getParent() == r->getParent()
				&& streamReadGetIsReliable(r)) {
			// the merged read is reliable only if all reads were reliable and all are in the same block
			// (if they were not in same block they are conditionally executed thus data may not be present)
			++reliableReadsCnt;
		} else {
			mergedReadIsReliable = false;
		}
	}

	assert(mergedDataBitWidth % 8 == 0);
	Builder.SetInsertPoint(reads[0]);
	auto streamPropsForMerged = streamProps.resize(mergedDataBitWidth);
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
		bool rDataAlwaysPresent = readIndex < reliableReadsCnt - 1;
		bool nextRDataAlwaysPresent = readIndex < reliableReadsCnt && readIndex < reliableReadsCnt - 1;
		auto partWordForR = mergedReadWord.slice(Builder, dataBitOffset,
				dataWidth,                                                 //
				/*isGuaranteedToBeNotEoF*/!rIsLast && nextRDataAlwaysPresent, //
				/*isGuarangeedToContainSomeData*/rDataAlwaysPresent       //
				);
		auto newR = partWordForR.flatten(Builder, nullptr);
		assert(newR->getType() == r->getType());
		newR->takeName(r);
		r->replaceAllUsesWith(newR);

		dataBitOffset += dataWidth;
		++readIndex;
	}
	for (auto r : reads) {
		r->eraseFromParent();
	}
	return mergedRead;
}

std::optional<StreamReadUntilEoFCFGFragment> StreamReadUntilEoFCFGFragment::detect(
		IRBuilderBase &Builder, BasicBlock &BlockWithRead) {
	StreamReadUntilEoFCFGFragment res;
	auto *BB = &BlockWithRead;
	llvm::SmallSet<BasicBlock*, 16> seen;

	for (;;) {
		if (seen.contains(BB)) {
			break;
		} else {
			seen.insert(BB);
		}

		// [todo] check that the first block dominates all others
		for (auto &I : *BB) {
			if (auto *CI = dyn_cast<CallInst>(&I)) {
				if (IsStreamRead(CI)
						&& (!res.ioPtr || CI->getArgOperand(0) == res.ioPtr)) {
					if (!res.ioPtr) {
						res.ioPtr = CI->getArgOperand(0);
					}
					SmallVector<CallInst*> readsToMerge;
					readsToMerge.push_back(CI);
					for (Instruction &I2 : make_range(
							I.getNextNode()->getIterator(), BB->end())) {
						if (auto *CI2 = dyn_cast<CallInst>(&I2)) {
							if (IsStreamRead(CI2)
									&& CI2->getArgOperand(0) == res.ioPtr) {
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
