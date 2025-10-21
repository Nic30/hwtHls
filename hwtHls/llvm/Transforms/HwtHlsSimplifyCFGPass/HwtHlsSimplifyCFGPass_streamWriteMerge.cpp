#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_streamWriteMerge.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PatternMatch.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/ValueTracking.h>
#include <llvm/Analysis/InstructionSimplify.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentOptionaStreamWrite.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_phiToLogicalExpr.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsImplication.h>
#include <hwtHls/llvm/Transforms/HwtHlsInstCombinePass/HwtHlsInstCombinerUtilsHoisting.h>

#include <hwtHls/llvm/targets/intrinsic/bitrange.h>
#include <hwtHls/llvm/targets/intrinsic/streamIo.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;
using namespace llvm::PatternMatch;


namespace hwtHls {

/*
 * Detect the sequence of optional streamWrite instructions in if-then like cfg
 * :note: first may have guard==nullptr if it is not optional
 * */
bool HwtHlsSimplifyCFGPass_streamWriteMergeDetect(
		llvm::BasicBlock &BBContainingStreamWrite,
		SmallVector<OptionalStreamWriteCFGFragment> &writeSeqeunceDown) {
	// detect linear sequences of optional writes
	// :note: lower bits of data are found first because they are
	// in blocks closer to entry
	auto wr = OptionalStreamWriteCFGFragment::detect(BBContainingStreamWrite);
	if (!wr.has_value())
		return false;
	if (!wr.value().containsOnlyStreamWrite(true))
		return false;

	// detect in up (def-use) direction
	BasicBlock *curEntry = wr.value().guard;
	Value *ioPtr = streamWriteGetIoArg(wr.value().write);
	// check that this is the top most optional write in chain
	if (curEntry->hasNPredecessors(2)
			&& any_of(predecessors(curEntry),
					[ioPtr](BasicBlock *BB) {
						auto predWr = OptionalStreamWriteCFGFragment::detect(
								*BB);
						return predWr.has_value()
								&& streamWriteGetIoArg(predWr.value().write)
										== ioPtr;
					})) {
		// if this is a case the parent section should trigger the rewrite
		return false; // this is to limit redoing of checks for sequences which can not be rewritten
	}
	// search non optional streamWrite in top block
	for (Instruction &I : reverse(*wr.value().guard)) {
		if (auto C = dyn_cast<CallInst>(&I)) {
			if (IsStreamWrite(C) && streamWriteGetIoArg(C) == ioPtr) {
				writeSeqeunceDown.push_back(
						OptionalStreamWriteCFGFragment(nullptr, C,
								wr.value().guard));
				break;
			}
		}
		if (!I.isTerminator() && !isSafeToSpeculativelyExecute(&I)
				&& !isa<AssumeInst>(&I)) {
			break;
		}
	}
	writeSeqeunceDown.push_back(wr.value());
	// search for successor writes
	for (;;) {
		BasicBlock *curExit = writeSeqeunceDown.back().exit;
		auto exitTerm = curExit->getTerminator();
		if (exitTerm->getNumSuccessors() != 2)
			break; // currently support only br, condbr
		// [todo] refactor 2x nearly same code
		auto wrT = OptionalStreamWriteCFGFragment::detect(
				*exitTerm->getSuccessor(0));
		if (wrT.has_value()) {
			OptionalStreamWriteCFGFragment &frag = wrT.value();
			if (streamWriteGetIoArg(frag.write) != ioPtr)
				break;
			if (!frag.containsOnlyStreamWrite())
				break;
			writeSeqeunceDown.push_back(frag);
		} else {
			auto wrF = OptionalStreamWriteCFGFragment::detect(
					*exitTerm->getSuccessor(1));
			if (wrF.has_value()) {
				OptionalStreamWriteCFGFragment &frag = wrF.value();
				if (streamWriteGetIoArg(frag.write) != ioPtr)
					break;
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

bool HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, llvm::SimplifyQuery &SQ,
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
	SmallVector<Value*> dataParts;
	SmallVector<Value*> maskParts;
	SmallVector<Value*> EoFs;
	SmallVector<Value*> WriteEns;
	LLVM_DEBUG(
			dbgs() << "HwtHlsSimplifyCFGPass_streamWriteMerge: attempting to merge "
					<< writeSeqenceDown.size()
					<< " writes together starting from "
					<< writeSeqenceDown[0].write->getParent()->getName() << "\n"
			; );
	auto &DT = DTU.getDomTree();
	for (const OptionalStreamWriteCFGFragment &wr : writeSeqenceDown) {
		if (&wr == &writeSeqenceDown.back() && dataParts.empty())
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

		Instruction* hoistPoint;
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
						; );
				if (dataParts.size() > 1) {
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
								Builder, DTU, SQ, writeSeqenceDownLeftover);
					}
					return false; // there may have been a change in expression but not in CFG
				}
			}
		}
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif
		// collect and hoist input args for partial write
		WriteEns.push_back(condition);
		auto data = streamWriteGetWriteData(wr.write);
		assert(hoistIntoDominatingBlock(*data, *hoistPoint, DT));
		dataParts.push_back(data);
		assert(data->getType()->getIntegerBitWidth() % 8 == 0);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

		size_t maskWidth = data->getType()->getIntegerBitWidth() / 8;
		auto mask = streamWriteGetWriteMaskOrEmpty(wr.write);
		if (mask)
			assert(hoistIntoDominatingBlock(*mask, *hoistPoint, DT));
		else
			mask = Builder.getInt(APInt::getAllOnes(maskWidth));
		mask = Builder.CreateSelect(condition, mask,
				Builder.getInt(APInt::getZero(maskWidth)));
		mask = attemptToSimplifyValue(mask, SQ);
		maskParts.push_back(mask);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

		auto eof = streamWriteGetWriteEoF(wr.write);
		assert(hoistIntoDominatingBlock(*eof, *hoistPoint, DT));
		EoFs.push_back(eof);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
		assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

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
		assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif
	}

	LLVM_DEBUG(
			dbgs() << "HwtHlsSimplifyCFGPass_streamWriteMerge: " << dataParts.size()
					<< " can be merged\n"
			; );
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif
	assert(dataParts.size() >= 2);
	BasicBlock *lastGuard = nullptr;
	SmallVector<OptionalStreamWriteCFGFragment> writeSeqenceDownLeftover;
	if (dataParts.size() != writeSeqenceDown.size()) {
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
		//	if (maskParts.size()) {
		//		assert(maskIt != maskParts.end());
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
		for (auto &wr : make_range(writeSeqenceDown.begin() + dataParts.size(),
				writeSeqenceDown.end())) {
			writeSeqenceDownLeftover.push_back(wr);
		}
		writeSeqenceDown.erase(writeSeqenceDown.begin() + dataParts.size(),
				writeSeqenceDown.end());
	}
	lastGuard = writeSeqenceDown.back().guard;
	Builder.SetInsertPoint(writeSeqenceDown.back().write);

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	assert(!verifyFunction(*Builder.GetInsertBlock()->getParent(), &errs()));
#endif

	// create one wider write in last write block in sequence
	Value *data = CreateBitConcat(&Builder, dataParts);
	Value *mask = CreateBitConcat(&Builder, maskParts);
	Value *EoF = Builder.CreateOr(EoFs);
	EoF = attemptToSimplifyValue(EoF, SQ);
	CreateStreamWrite(&Builder, streamWriteGetIoArg(writeSeqenceDown[0].write),
			data, mask, EoF);

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
		HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(Builder, DTU, SQ,
				writeSeqenceDownLeftover);
	}

	return true;
}

bool HwtHlsSimplifyCFGPass_streamWriteMerge(IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, llvm::BasicBlock &BBContainingStreamWrite,
		llvm::SimplifyQuery &SQ) {
	SmallVector<OptionalStreamWriteCFGFragment> writeSeqenceDown;
	if (!HwtHlsSimplifyCFGPass_streamWriteMergeDetect(BBContainingStreamWrite,
			writeSeqenceDown))
		return false;
	return HwtHlsSimplifyCFGPass_streamWriteMerge_rewrite(Builder, DTU, SQ,
			writeSeqenceDown);
}

}

