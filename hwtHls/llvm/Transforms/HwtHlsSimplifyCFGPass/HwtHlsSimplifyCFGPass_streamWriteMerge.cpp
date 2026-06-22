#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/InstructionSimplify.h>

#include <hwtHls/llvm/intrinsic/metadataSideEffect.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentOptionaStreamWrite.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentStreamWriteVariableLen.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_phiToLogicalExpr.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsHoisting.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/streamIoLoweringPass/StreamChannelProps.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

Value* attemptToSimplifyValue(Value *V, llvm::SimplifyQuery &SQ) {
	if (auto *I = dyn_cast<Instruction>(V)) {
		if (auto PHI = dyn_cast<PHINode>(V)) {
			// attempt to optimize operands of the condition phi
			for (auto &V : PHI->incoming_values()) {
				if (auto VI = dyn_cast<Instruction>(V.get())) {
					if (Value *NewV = simplifyInstruction(VI, SQ)) {
						VI->replaceAllUsesWith(NewV);
						VI->eraseFromParent();
					}
				}
			}

			//if (Value* replacement = HwtHlsSimplifyCFGPass_phiToLogicalExpr(*PHI)) {
			//	PHI->replaceAllUsesWith(replacement);
			//	PHI->eraseFromParent();
			//	condition = replacement;
			//}
		}

		if (Value *simplified = simplifyInstruction(I, SQ)) {
			I->replaceAllUsesWith(simplified);
			if (!simplified->hasName()) {
				if (auto simplifiedI = dyn_cast<Instruction>(simplified)) {
					simplifiedI->takeName(I);
				}
			}
			I->eraseFromParent();
			V = simplified;
		}
	}
	return V;
}

class StreamWordParts {
public:
	SmallVector<Value*> data;
	SmallVector<Value*> maskOrEmpty;
	SmallVector<Value*> SoF;
	SmallVector<Value*> EoF;
	SmallVector<Value*> Error;
};

CallInst* CreateStreamWriteFromParts(
		const StreamWordParts &parts, IRBuilderBase &Builder,
		StreamChannelProps &streamProps, llvm::SimplifyQuery &SQ,
		Value *StreamIoArg) {
	// create one wider write in last write block in sequence
	Value *data = CreateBitConcat(&Builder, parts.data);
	Value *maskOrEmpty = nullptr;
	switch (streamProps.byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		break;
	case ByteEnableEncoding::BEE_MASK:
		if (streamProps.hasMask())
			maskOrEmpty = CreateBitConcat(&Builder, parts.maskOrEmpty);
		break;
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		if (streamProps.hasEmpty()) {
			auto emptyWidth = streamProps.getWidthOfEmptyForData(
					data->getType()->getIntegerBitWidth(),
					streamProps.byteWidth, streamProps.supportZLP);
			auto emptyTy = Builder.getIntNTy(emptyWidth);
			for (auto m : parts.maskOrEmpty) {
				m = Builder.CreateZExt(m, emptyTy);
				if (maskOrEmpty)
					maskOrEmpty = Builder.CreateAdd(maskOrEmpty, m);
				else
					maskOrEmpty = m;
			}
		}
		break;
	}
	}
	Value *SoF = streamProps.hasSoF() ? Builder.CreateOr(parts.SoF) : nullptr;
	Value *EoF = streamProps.hasEoF() ? Builder.CreateOr(parts.EoF) : nullptr;
	Value *Error =
			streamProps.hasError() ? Builder.CreateOr(parts.Error) : nullptr;
	if (SoF)
		SoF = attemptToSimplifyValue(SoF, SQ);
	if (EoF)
		EoF = attemptToSimplifyValue(EoF, SQ);
	if (Error)
		Error = attemptToSimplifyValue(Error, SQ);
	return CreateStreamWrite(&Builder, StreamIoArg, data, maskOrEmpty, SoF, EoF,
			Error);
}

void HwtHlsSimplifyCFGPass_streamWriteMerge_collectValuePartsFromWriteForMerging(
		IRBuilderBase &Builder, StreamChannelProps &streamProps,
		llvm::SimplifyQuery &SQ, CallInst *write, Value *enableCondition, //
		Instruction *hoistPoint, DominatorTree *DT,  //
		StreamWordParts &parts) {
	if (hoistPoint)
		assert(DT && "DominatorTree is required for hoisting of values");
	auto data = streamWriteGetWriteData(write);
	if (hoistPoint && !hoistIntoDominatingBlock(*data, *hoistPoint, *DT)) {
		llvm_unreachable(
				"NotImplemented: Handle the case where it is not possible to hoist data");
	}
	parts.data.push_back(data);
	assert(data->getType()->getIntegerBitWidth() % streamProps.byteWidth == 0);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

	Value *maskOrEmpty = streamWriteGetWriteMaskOrEmpty(write);
	if (maskOrEmpty && hoistPoint
			&& !hoistIntoDominatingBlock(*maskOrEmpty, *hoistPoint, *DT)) {
		llvm_unreachable(
				"NotImplemented: Handle the case where it is not possible to hoist maskOrEmpty");
	}

	size_t wordByteCnt = data->getType()->getIntegerBitWidth()
			/ streamProps.byteWidth;
	switch (streamProps.byteEnableEncoding) {
	case ByteEnableEncoding::BEE_NONE:
		maskOrEmpty = nullptr;
		break;
	case ByteEnableEncoding::BEE_MASK: {
		if (!maskOrEmpty)
			maskOrEmpty = Builder.getInt(APInt::getAllOnes(wordByteCnt)); // no mask == all bytes always valid
		maskOrEmpty = Builder.CreateSelect(enableCondition, maskOrEmpty,
				Builder.getInt(APInt::getZero(wordByteCnt)));
		maskOrEmpty = attemptToSimplifyValue(maskOrEmpty, SQ);
		break;
	}
	case ByteEnableEncoding::BEE_ENABLE_PLUS_EMPTY: {
		size_t emptyWidth = streamProps.getWidthOfEmptyForData(
				data->getType()->getIntegerBitWidth(), streamProps.byteWidth,
				true);
		if (!maskOrEmpty)
			maskOrEmpty = Builder.getInt(APInt::getZero(emptyWidth)); // no empty == all bytes always valid
		maskOrEmpty = Builder.CreateSelect(enableCondition, maskOrEmpty,
				Builder.getIntN(wordByteCnt, emptyWidth));
		maskOrEmpty = attemptToSimplifyValue(maskOrEmpty, SQ);
		break;
	}
	default:
		llvm_unreachable("Unknown encoding of ByteEnableEncoding");
	}

	parts.maskOrEmpty.push_back(maskOrEmpty);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

	if (streamProps.errorWidth) {
		Value *error = streamWriteGetWriteError(write);
		if (!error) {
			error = Builder.getInt(APInt::getZero(streamProps.errorWidth));
		} else {
			assert(
					error->getType()->getIntegerBitWidth()
							== streamProps.errorWidth);
		}
		parts.Error.push_back(error);
	}

	auto sof = streamWriteGetWriteSoF(write);
	if (maskOrEmpty && hoistPoint
			&& !hoistIntoDominatingBlock(*sof, *hoistPoint, *DT)) {
		llvm_unreachable(
				"NotImplemented: Handle the case where it is not possible to hoist sof");
	}
	parts.SoF.push_back(sof);

	auto eof = streamWriteGetWriteEoF(write);
	if (maskOrEmpty && hoistPoint
			&& !hoistIntoDominatingBlock(*eof, *hoistPoint, *DT)) {
		llvm_unreachable(
				"NotImplemented: Handle the case where it is not possible to hoist eof");
	}
	parts.EoF.push_back(eof);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif
}

llvm::CallInst* HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock_known(
		llvm::IRBuilderBase &Builder, llvm::SimplifyQuery &SQ,
		SmallVector<CallInst*> writesToSameIo, Value *ioArg,
		StreamChannelProps &streamProps) {
	StreamWordParts parts;
	auto True = Builder.getTrue();
	Builder.SetInsertPoint(writesToSameIo.back()->getNextNode());
	for (auto &wr : writesToSameIo) {
		HwtHlsSimplifyCFGPass_streamWriteMerge_collectValuePartsFromWriteForMerging(
				Builder, streamProps, SQ, wr, True, nullptr, nullptr, parts);
	}
	auto newWr = CreateStreamWriteFromParts(parts, Builder, streamProps, SQ,
			ioArg);
	for (auto &wr : writesToSameIo) {
		wr->eraseFromParent();
	}
	return newWr;
}

llvm::CallInst* HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock(
		llvm::IRBuilderBase &Builder,
		llvm::BasicBlock &BBPossiblyContainingStreamWrite,
		llvm::SimplifyQuery &SQ) {
	SmallVector<std::pair<Value*, CallInst*>> writes;
	for (auto &I : BBPossiblyContainingStreamWrite) {
		if (auto *CI = dyn_cast<CallInst>(&I)) {
			if (IsStreamWrite(CI)) {
				auto ioArg = streamWriteGetIoArg(CI);
				writes.push_back( { ioArg, CI });
			}
		}
	}
	if (writes.empty()) {
		return nullptr;
	} else if (writes.size() == 1) {
		return writes[0].second;
	}
	llvm::CallInst *lastlyMergedStreamWrite = nullptr;
	for (auto w0 = writes.begin(); w0 != writes.end(); ++w0) {
		if (!w0->first)
			continue; // already merged item

		Value *ioArg = w0->first;
		SmallVector<CallInst*> writesToSameIo;
		for (auto w1 = w0; w1 != writes.end(); ++w1) {
			if (w1->first != ioArg)
				continue; // skip writes for different io stream
			writesToSameIo.push_back(w1->second);
			*w1 = { nullptr, nullptr };
		}
		if (writesToSameIo.size() > 1) {
			llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
			StreamChannelProps streamProps = findStreamIoPropsInMetadata(
					*BBPossiblyContainingStreamWrite.getParent(), ioArg,
					GeneratedAllocas);
			lastlyMergedStreamWrite =
					HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock_known(
							Builder, SQ, writesToSameIo, ioArg, streamProps);
		}
	}

	return lastlyMergedStreamWrite;
}
std::optional<OptionalStreamWriteCFGFragment> OptionalStreamWriteCFGFragment_detectAndMergeInBB(
		IRBuilderBase &Builder, llvm::SimplifyQuery &SQ, BasicBlock &BB,
		Value *ioPtr) {
	llvm::CallInst *wr0 = HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock(
			Builder, BB, SQ);
	// find next stream write in this block if the first one was not the write for this ioPtr
	while (wr0 && streamWriteGetIoArg(wr0) != ioPtr) {
		for (auto nextWr = wr0->getNextNode();; nextWr =
				nextWr->getNextNode()) {
			if (!nextWr) {
				wr0 = nullptr;
				break;
			}
			auto nextCallI = dyn_cast<CallInst>(nextWr);
			if (!nextCallI || IsStreamWrite(nextCallI)) {
				wr0 = nextCallI;
				break;
			}
		}
	}
	if (!wr0)
		return {};

	auto wrT = OptionalStreamWriteCFGFragment::detect(*wr0);
	return wrT;
}
/*
 * Detect the sequence of optional streamWrite instructions in if-then like cfg
 * :note: first may have guard==nullptr if it is not optional
 * */
bool HwtHlsSimplifyCFGPass_streamWriteMergeDetectAndMergeInSameBB(
		IRBuilderBase &Builder, llvm::SimplifyQuery &SQ, llvm::CallInst &wr0,
		SmallVector<OptionalStreamWriteCFGFragment> &writeSeqeunceDown) {
	// detect linear sequences of optional writes
	// :note: lower bits of data are found first because they are
	// in blocks closer to entry
	auto _wr = OptionalStreamWriteCFGFragment::detect(wr0);
	if (!_wr.has_value())
		return false;
	OptionalStreamWriteCFGFragment &wr = _wr.value();
	if (!wr.containsOnlyStreamWrite(true))
		return false;

	// detect in up (def-use) direction
	BasicBlock *curEntry = wr.guard;
	Value *ioPtr = streamWriteGetIoArg(wr.write);
	// check that this is the top most optional write in chain
	if (curEntry->hasNPredecessors(2)
			&& any_of(predecessors(curEntry),
					[&Builder, &SQ, ioPtr](BasicBlock *BB) {
						auto predWr =
								OptionalStreamWriteCFGFragment_detectAndMergeInBB(
										Builder, SQ, *BB, ioPtr);
						return predWr.has_value();
					})) {
		// if this is a case the parent section should trigger the rewrite
		return false; // this is to limit redoing of checks for sequences which can not be rewritten
	}
	// search non optional streamWrite in top block
	for (Instruction &I : reverse(*wr.guard)) {
		if (auto C = dyn_cast<CallInst>(&I)) {
			if (IsStreamWrite(C) && streamWriteGetIoArg(C) == ioPtr) {
				writeSeqeunceDown.push_back(
						OptionalStreamWriteCFGFragment(nullptr, C, wr.guard));
				break;
			}
		}
		if (!I.isTerminator() && !isSafeToSpeculativelyExecute(&I)
				&& !isa<AssumeInst>(&I)) {
			break;
		}
	}
	writeSeqeunceDown.push_back(wr);
	// search for successor writes
	for (;;) {
		BasicBlock *curExit = writeSeqeunceDown.back().exit;
		auto exitTerm = curExit->getTerminator();
		if (exitTerm->getNumSuccessors() != 2)
			break; // currently support only br, condbr
		// [todo] refactor 2x nearly same code
		auto wrT = OptionalStreamWriteCFGFragment_detectAndMergeInBB(Builder,
				SQ, *exitTerm->getSuccessor(0), ioPtr);
		if (wrT.has_value()) {
			OptionalStreamWriteCFGFragment &frag = wrT.value();
			if (!frag.containsOnlyStreamWrite())
				break;
			writeSeqeunceDown.push_back(frag);
		} else {
			auto wrF = OptionalStreamWriteCFGFragment_detectAndMergeInBB(
					Builder, SQ, *exitTerm->getSuccessor(1), ioPtr);
			if (wrF.has_value()) {
				OptionalStreamWriteCFGFragment &frag = wrF.value();
				if (!frag.containsOnlyStreamWrite())
					break;
				writeSeqeunceDown.push_back(frag);
			} else {
				break;
			}
		}
	}
	if (writeSeqeunceDown.size() < 2) {
		return false;
	}
	return true;
}

bool HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, llvm::SimplifyQuery &SQ,
		StreamChannelProps &streamProps,
		SmallVector<OptionalStreamWriteCFGFragment> &writeSeqenceDown) {
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(DTU.getDomTree().verify());
	assert(
			!verifyFunction(
					*writeSeqenceDown[0].write->getParent()->getParent(),
					&errs()));
#endif
	// if write enable condition implies the write enable condition of successor the merge is possible
	Value *lastCondition = nullptr;
	bool lastConditionIsNegated = false;
	//BasicBlock *writeSectionEntryBB = writeSeqeunceDown[0].guard;
	// :note: all concatenation vectors in lower bits first format
	SmallVector<Value*> WriteEns;
	StreamWordParts parts;
	LLVM_DEBUG(
			dbgs()
					<< "HwtHlsSimplifyCFGPass_streamWriteMerge: attempting to merge "
					<< writeSeqenceDown.size()
					<< " writes together starting from "
					<< writeSeqenceDown[0].write->getParent()->getName() << "\n"
			;
	);
	auto &DT = DTU.getDomTree();
	for (const OptionalStreamWriteCFGFragment &wr : writeSeqenceDown) {
		if (&wr == &writeSeqenceDown.back() && parts.data.empty())
			return false; // there is nothing to merge with because we did not collect any other write and we are at last one
		Value *condition = nullptr;
		bool conditionIsNegated = false;
		std::tie(condition, conditionIsNegated) = wr.getWriteEnableCondition();
		// attempt to simplify condition
		condition = attemptToSimplifyValue(condition, SQ);
		//if (lastConditionIsNegated) {
		//	if (auto lastConditionI = dyn_cast<Instruction>(lastCondition)) {
		//		Builder.SetInsertPoint(lastConditionI);
		//		lastCondition = Builder.CreateNot(lastConditionI);
		//
		//	} else {
		//		llvm_unreachable(
		//				"NotImplemented - constant condition in last guard block terminator");
		//	}
		//}

		Instruction *hoistPoint;
		if (wr.guard)
			hoistPoint = wr.guard->getTerminator();
		else
			hoistPoint = wr.write;
		Builder.SetInsertPoint(hoistPoint);

		if (lastCondition != nullptr) {
			// if this is not first fragment
			// check if later write may be executed only if previous write was executed
			if (!isImpliedConditionAndOrTree(Builder, condition, lastCondition,
					SQ.DL, SQ.AC, SQ.DT, writeSeqenceDown.back().write)) {
				LLVM_DEBUG(
						dbgs()
								<< "HwtHlsSimplifyCFGPass_streamWriteMerge: can not prove implication (condition ==> lastCondition)"
								<< *condition << " ==> " << *lastCondition
								<< "\n"
						;
				);
				if (parts.data.size() > 1) {
					break; // merge at least parts which were found to be mergable and then process leftover
				} else {
					// can not extract currently selected parts, try without this fragment
					SmallVector<OptionalStreamWriteCFGFragment> writeSeqenceDownLeftover;
					for (auto &wr : make_range(writeSeqenceDown.begin() + 1,
							writeSeqenceDown.end())) {
						writeSeqenceDownLeftover.push_back(wr);
					}
					if (writeSeqenceDownLeftover.size() > 1) {
						// there is still enough fragments to try merge
						return HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(
								Builder, DTU, SQ, streamProps,
								writeSeqenceDownLeftover);
					}
					return false; // there may have been a change in expression but not in CFG
				}
			}
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(
				!verifyFunction(*Builder.GetInsertBlock()->getParent(),
						&errs()));
#endif
		// collect and hoist input args for partial write
		Value *_condition = condition;
		if (conditionIsNegated) {
			_condition = Builder.CreateNot(condition);
		}
		WriteEns.push_back(_condition);
		HwtHlsSimplifyCFGPass_streamWriteMerge_collectValuePartsFromWriteForMerging(
				Builder, streamProps, SQ, wr.write, _condition, hoistPoint, &DT,
				parts);
		if (lastConditionIsNegated) {
			if (lastCondition->hasNUses(0)) {
				if (auto lastConditionI = dyn_cast<Instruction>(
						lastCondition)) {
					// erase temporally generated negation
					lastConditionI->eraseFromParent();
				}
			}
		}

		lastCondition = condition;
		lastConditionIsNegated = conditionIsNegated;
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(
				!verifyFunction(*Builder.GetInsertBlock()->getParent(),
						&errs()));
#endif
	}

	LLVM_DEBUG(
			dbgs() << "HwtHlsSimplifyCFGPass_streamWriteMerge: "
					<< parts.data.size() << " can be merged\n");
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif
	assert(parts.data.size() >= 2);
	BasicBlock *lastGuard = nullptr;
	SmallVector<OptionalStreamWriteCFGFragment> writeSeqenceDownLeftover;
	if (parts.data.size() != writeSeqenceDown.size()) {
		// the merging ended prematurely, we need to hoist newly generated instructions before last write which will be extracted

		//auto lastGuardTerm = lastGuard->getTerminator();
		//auto &DT = DTU.getDomTree();
		//auto dataIt = dataParts.begin();
		//auto maskIt = maskParts.begin();
		//auto EoFIt = EoFs.begin();
		//for (OptionalStreamWriteCFGFragment &frag : make_range(
		//		writeSeqenceDown.begin(),
		//		writeSeqenceDown.begin() + dataParts.size())) {
		//	auto GuardTerm = frag.guard->getTerminator();
		//	assert(GuardTerm);
		//
		//	hoistOnEndOfDominatingBlock(**dataIt, *GuardTerm, DT);
		//	++dataIt;
		//
		//	if (maskOrEmptyParts.size()) {
		//		assert(maskIt != maskOrEmptyParts.end());
		//		hoistOnEndOfDominatingBlock(**maskIt, *GuardTerm, DT);
		//		++maskIt;
		//	}
		//	if (EoFs.size()) {
		//		assert(EoFIt != EoFs.end());
		//		hoistOnEndOfDominatingBlock(**EoFIt, *GuardTerm, DT);
		//		++EoFIt;
		//	}
		//}
		// remove writes which can not be merged
		for (auto &wr : make_range(writeSeqenceDown.begin() + parts.data.size(),
				writeSeqenceDown.end())) {
			writeSeqenceDownLeftover.push_back(wr);
		}
		writeSeqenceDown.erase(writeSeqenceDown.begin() + parts.data.size(),
				writeSeqenceDown.end());
	}
	OptionalStreamWriteCFGFragment &wr0 = writeSeqenceDown.front();
	OptionalStreamWriteCFGFragment &wrLast = writeSeqenceDown.back();
	// construct merged write in exit block which is post-dominating all blocks
	assert(wrLast.exit->hasNPredecessors(2));

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

	lastGuard = wrLast.guard;
	// create one wider write in last write block in sequence

	Value *ioArg = streamWriteGetIoArg(wr0.write);
	{
		// construct "if (first byte enable) then write" to avoid write without any valid bytes
		Value *writeEn;
		bool writeEnIsNegated;
		std::tie(writeEn, writeEnIsNegated) = wr0.getWriteEnableCondition();
		Builder.SetInsertPoint(wrLast.exit->getFirstInsertionPt());
		if (writeEnIsNegated) {
			writeEn = Builder.CreateNot(writeEn);
		}
		auto newWrBBTerm = SplitBlockAndInsertIfThen(writeEn,
				wrLast.exit->getFirstInsertionPt(), false, nullptr, &DTU);
		// newWrBBTerm->getParent()->setName(wrLast.exit->getName() + ".streamWrMerge");
		Builder.SetInsertPoint(newWrBBTerm);
	}
	CreateStreamWriteFromParts(parts,
			Builder, streamProps, SQ, ioArg);
	// delete original part writes
	for (const OptionalStreamWriteCFGFragment &wr : writeSeqenceDown) {
		wr.write->eraseFromParent();
	}
	// update condition of a new write
	Instruction *lastGuardBBTerm = lastGuard->getTerminator();
	Builder.SetInsertPoint(lastGuardBBTerm);
	// Value *writeEn = Builder.CreateOr(WriteEns);
	//writeEn = attemptToSimplifyValue(writeEn, SQ);

	dyn_cast<BranchInst>(lastGuardBBTerm)->setCondition(WriteEns[0]); // it is proven that WriteEns[0] is 1 if any WriteEns is 1
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif
	if (writeSeqenceDownLeftover.size() > 1) {
		assert(
				HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(Builder, DTU, SQ,
						streamProps, writeSeqenceDownLeftover));
	}

	return true;
}

static bool canHoistAllUnrelatedInstrucitionsInWriteUntilEoFPattern(
		ArrayRef<
				CfgFragmentStreamWriteVariableLen::BasicBlockWithStreamWriteAndBrCond> blocks) {
	// forward check that the block do not contain any instruction between
	// which would prevent merging
	for (auto &BBfrag : blocks) {
		if (&BBfrag == &*blocks.begin()) {
			// in the top block there may be instructions before stream write which stay in place
			// and we have to check only instructions after write
			assert(BBfrag.streamWrite->getParent() == BBfrag.BB);
			auto afterWrIt = BBfrag.streamWrite->getNextNode()->getIterator();
			auto bbTermIt = BBfrag.BB->getTerminator()->getIterator();
			for (Instruction &I : make_range(afterWrIt, bbTermIt)) {
				if (I.isTerminator())
					break;
				assert(&I != BBfrag.streamWrite);
				if ((I.mayHaveSideEffects() || I.isVolatile())
						&& !hasMetadataSideeffectAllowHoist(I)) {
					return false;
				}
			}
		} else {
			// in other blocks we have to hoist everything
			// the streamWrite may have no users, so all other instructions (except terminator)
			// must be hoistable
			for (auto &I : *BBfrag.BB) {
				if (I.isTerminator())
					break;
				if (&I == BBfrag.streamWrite)
					continue;
				if (!isa<PHINode>(&I) || I.mayHaveSideEffects()
						|| I.isVolatile()) {
					return false;
				}
			}
		}
	}
	return true;
}

static void hoistAllUnrelatedInstrucitionsInWriteUntilEoFPattern(
		ArrayRef<
				CfgFragmentStreamWriteVariableLen::BasicBlockWithStreamWriteAndBrCond> blocks) {
	auto &BB0 = *blocks.begin()->BB;
	// hoist all instructions to BB0
	for (auto &BBfrag : blocks) {
		if (&BBfrag == &*blocks.begin()) {
			// in BB0
			assert(BBfrag.streamWrite->getParent() == BBfrag.BB);
			assert(BBfrag.BB == &BB0);
			auto wrIt = BBfrag.streamWrite->getIterator();
			auto afterWrIt = wrIt;
			++afterWrIt;
			auto bbTermIt = BB0.getTerminator()->getIterator();
			if (afterWrIt != bbTermIt) {
				// if write is not followed by terminator (if there is something to hoist)
				// move everything after write before write
				BB0.splice(wrIt, &BB0, afterWrIt, bbTermIt);
			}
			assert(BB0.getTerminator()->getPrevNode() == BBfrag.streamWrite);
		} else {
			// hoist all other non-terminal instructions before terminal in BB0
			BB0.splice(BB0.getTerminator()->getIterator(), BBfrag.BB,
					BBfrag.BB->begin()->getIterator(),
					BBfrag.BB->getTerminator()->getIterator());
		}
	}
}

static bool HwtHlsSimplifyCFGPass_streamWriteMerge_variableLenWrite(
		IRBuilderBase &Builder, 
		llvm::SimplifyQuery &SQ, llvm::CallInst *wr0) {

	llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
	auto wrSequence = CfgFragmentStreamWriteVariableLen::detect(Builder, SQ,
			*wr0->getParent(),
			*wr0->getParent()->getTerminator()->getSuccessor(0));
	if (wrSequence.has_value() && wrSequence.value().blocks.size() > 1) {
		auto &blocks = wrSequence.value().blocks;
		bool isWriteUntilEof = true;
		for (auto &BBfrag : blocks) {
			if (!BBfrag.toExitBrCond && &BBfrag == &blocks.back()) {
				break; // allow unconditional branch in last case
				// it means that the write block always jumps to exit block
			}
			// must be in format if eof then exit else continue to next write
			if (BBfrag.toExitBrCondIsNegated
					|| BBfrag.toExitBrCond
							!= streamWriteGetWriteEoF(BBfrag.streamWrite)) {
				isWriteUntilEof = false;
				break;
			}
		}
		if (isWriteUntilEof) {
			if (!canHoistAllUnrelatedInstrucitionsInWriteUntilEoFPattern(
					blocks))
				return false;

			hoistAllUnrelatedInstrucitionsInWriteUntilEoFPattern(blocks);
			auto &BB0 = *blocks.begin()->BB;
			auto streamIoArg = wrSequence.value().streamIoPtr;
			StreamChannelProps streamProps = findStreamIoPropsInMetadata(
					*BB0.getParent(), streamIoArg, GeneratedAllocas);
			Builder.SetInsertPoint(blocks.begin()->streamWrite);

			StreamWordParts parts;

			Value *wrEn = Builder.getTrue();
			// everything was hoisted it is now safe to construct this variable length write after the first write
			for (auto &BBfrag : blocks) {
				assert(
						&*Builder.GetInsertPoint()
								== blocks.begin()->streamWrite);
				HwtHlsSimplifyCFGPass_streamWriteMerge_collectValuePartsFromWriteForMerging(
						Builder, streamProps, SQ, BBfrag.streamWrite, wrEn,
						nullptr, nullptr, parts);
				if (&BBfrag == &blocks.back())
					break;
				// wrEn must be 1 if write should continue
				auto prevWrEn = wrEn;
				if (BBfrag.toExitBrCondIsNegated) {
					wrEn = BBfrag.toExitBrCond; // 1 means non-exit
				} else {
					wrEn = Builder.CreateNot(BBfrag.toExitBrCond); // 0 means non-exit
				}
				if (auto wrEnI = dyn_cast<Instruction>(wrEn)) {
					auto knownToBeDependentOnWrEn = isImpliedConditionAndOrTree(
							Builder, prevWrEn, wrEn, SQ.DL, SQ.AC, SQ.DT,
							wrEnI);
					if (!knownToBeDependentOnWrEn.has_value()
							|| !knownToBeDependentOnWrEn.value()) {
						// and with enable for previous chunk only if the condition is not already anded with it
						wrEn = Builder.CreateAnd(prevWrEn, wrEn);
					}
				} else {
					wrEn = Builder.CreateAnd(prevWrEn, wrEn);
				}
			}

			assert(Builder.GetInsertBlock() == &BB0);
			CreateStreamWriteFromParts(parts, Builder, streamProps, SQ, streamProps.ioArg);
			//BB0.getParent()->dump();
			//for (auto &BBfrag : blocks) {
			//	errs() << *BBfrag.streamWrite << "\n";
			//}
			for (auto &BBfrag : blocks) {
				BBfrag.streamWrite->eraseFromParent();
			}
			return true;
		}

		// [todo] check that enable for previous streamWrite is implied by this stream write
		// (previous stream write is always enabled if this is enabled)
	}
	return false;
}

bool HwtHlsSimplifyCFGPass_streamWriteMerge(IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BBMaybeContainingStreamWrite,
		llvm::SimplifyQuery &SQ) {
	auto wr0 = HwtHlsSimplifyCFGPass_streamWriteMergeInSingleBlock(Builder,
			BBMaybeContainingStreamWrite, SQ);
	if (!wr0)
		return false;
	SmallVector<OptionalStreamWriteCFGFragment> writeSeqenceDown;
	if (HwtHlsSimplifyCFGPass_streamWriteMergeDetectAndMergeInSameBB(Builder,
			SQ, *wr0, writeSeqenceDown)) {
		assert(writeSeqenceDown.size());
		llvm::SmallVector<llvm::AllocaInst*> GeneratedAllocas;
		StreamChannelProps streamProps = findStreamIoPropsInMetadata(
				*BBMaybeContainingStreamWrite.getParent(),
				streamWriteGetIoArg(wr0), GeneratedAllocas);
		return HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(Builder, DTU, SQ,
				streamProps, writeSeqenceDown);

	} else if (HwtHlsSimplifyCFGPass_streamWriteMerge_variableLenWrite(Builder,
			SQ, wr0)) {
		return true;
	}
	return false;
}

}
