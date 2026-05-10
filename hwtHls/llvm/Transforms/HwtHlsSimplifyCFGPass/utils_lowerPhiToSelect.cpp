#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>

#include <cassert>

#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>

using namespace llvm;

namespace hwtHls {

bool LowerPhisToSelectInRegionContext::analyze() {
	// auto exitBBAfterPhis = exitBB.getFirstNonPHIIt();
	bbsWhichMustPreservePhis.insert(exitBBs.begin(), exitBBs.end());
	bbsWhichMustPreservePhis.insert(&BB0);
	topologicalSortForBlocks(allBBsOfRegion, &BB0);


	if (exitBBs.size() > 1) {
		assert(exitBBs.size() == 2);
		// assert that the exitBB0 is topologically before exitBB1
		if (exitBBs[0] == &BB0) {
		} else if (hasSuccessorFromRegion(exitBBs[1])) {
			// swap items in exitBBs
			auto e1 = exitBBs.pop_back_val();
			auto e0 = exitBBs.pop_back_val();
			assert((e1 == &BB0 || !hasSuccessorFromRegion(e0)) &&
				   "There should not be any loop between the exit blocks");
			exitBBs.insert(e1);
			exitBBs.insert(e0);
		}
		if (exitBBs[0] != &BB0) {
			// localize blocks between exits
			// because we will have to sink part of instructions to exit1
			findBlocksBetweenExitBlocksOfRegion(allBBsOfRegion, exitBBs,
												betweenExitBBs);
			if (!betweenExitBBs.empty())
				topologicalSortForBlocks(betweenExitBBs);
			for (auto &I : *exitBBs[0]) {
				valuesAfffectedByExit0.insert(&I);
			}
		}
	}
	if (all_of(allBBsOfRegion,
			   [](BasicBlock *BB) { return BB->phis().empty(); })) {
		if (!hasPredecessorFromRegion(&BB0) || BB0.phis().empty()) {
			return false; // no phis to lower
		}
	}
	return true;
}

Value *constructBranchConditionToBB(llvm::IRBuilderBase &Builder,
									BasicBlock &SrcBB, BasicBlock &DstBB,
									const SetVector<BasicBlock *> &handleBBs,
									bool ignoreCheckForDstAndHandle) {
	if (!ignoreCheckForDstAndHandle) {
		if (&SrcBB == &DstBB) {
			return Builder.getTrue();
		} else if (handleBBs.contains(&SrcBB)) {
			return Builder.getFalse(); // CFG reached some other handleBB first
		}
	}
	auto t = SrcBB.getTerminator();
	if (isa<UnreachableInst>(t)) {
		return Builder.getFalse();
	} else if (auto br = dyn_cast<BranchInst>(t)) {
		if (br->isConditional()) {
			auto t = constructBranchConditionToBB(Builder, *br->getSuccessor(0),
												  DstBB, handleBBs, false);
			auto f = constructBranchConditionToBB(Builder, *br->getSuccessor(1),
												  DstBB, handleBBs, false);
			return Builder.CreateSelect(br->getCondition(), t, f);
		} else {
			return constructBranchConditionToBB(Builder, *br->getSuccessor(0),
												DstBB, handleBBs, false);
		}
	} else if (auto sw = dyn_cast<SwitchInst>(t)) {
		auto res = constructBranchConditionToBB(Builder, *sw->getDefaultDest(),
												DstBB, handleBBs, false);
		for (auto &c : sw->cases()) {
			auto eq =
				Builder.CreateICmpEQ(sw->getCondition(), c.getCaseValue());
			auto cV = constructBranchConditionToBB(
				Builder, *c.getCaseSuccessor(), DstBB, handleBBs, false);
			res = Builder.CreateSelect(eq, cV, res);
		}
		return res;
	} else {
		llvm_unreachable("NotImplemented: unsupported terminator");
	}
}

Value *constructBranchConditionToBBDirect(llvm::IRBuilderBase &Builder,
										  BasicBlock &SrcBB,
										  BasicBlock &DstBB) {
	auto t = SrcBB.getTerminator();
	if (auto br = dyn_cast<BranchInst>(t)) {
		if (br->isConditional()) {
			auto C = br->getCondition();
			if (br->getSuccessor(0) == &DstBB) {
				if (br->getSuccessor(1) == &DstBB) {
					// SrcBB br C, DstBB, DstBB
					return Builder.getTrue();
				} else {
					// SrcBB br C, DstBB, xBB
					return C;
				}
			} else {
				// SrcBB br C, xBB, DstBB
				assert(br->getSuccessor(1) == &DstBB);
				return Builder.CreateNot(C);
			}
		} else {
			// SrcBB br DstBB
			assert(br->getSuccessor(0) == &DstBB);
			return Builder.getTrue();
		}
	} else if (auto sw = dyn_cast<SwitchInst>(t)) {
		SmallVector<Value *>
			otherBrConditions; // conditions for cases not jumping to DstBB
		SmallVector<Value *>
			brSuccessConditions; // conditions for cases jumping to DstBB
		// if dstIsSwDefault then we have to collect all otherBrConditions
		bool dstIsSwDefault = sw->getDefaultDest() == &DstBB;

		for (auto &c : sw->cases()) {
			bool isCaseForDstBB = c.getCaseSuccessor() == &DstBB;
			if (isCaseForDstBB || dstIsSwDefault) {
				auto eq =
					Builder.CreateICmpEQ(sw->getCondition(), c.getCaseValue());
				if (isCaseForDstBB) {
					brSuccessConditions.push_back(eq);
				} else {
					otherBrConditions.push_back(eq);
				}
			}
		}
		Value *sucBr;
		if (brSuccessConditions.empty()) {
			sucBr = Builder.getFalse();
		} else {
			sucBr = Builder.CreateOr(brSuccessConditions);
		}
		Value *res;
		if (dstIsSwDefault) {
			if (otherBrConditions.empty()) {
				// switch with case which all leading to the same dst as switch
				// default (which is DstBB)
				res = Builder.getTrue();
			} else {
				// there are some cases which are not leading to DstBB
				Value *brDefault =
					Builder.CreateNot(Builder.CreateOr(otherBrConditions));
				res = Builder.CreateOr(sucBr, brDefault);
			}
		} else {
			res = sucBr;
		}
		return res;
	} else {
		llvm_unreachable("NotImplemented: unsupported terminator");
	}
}

void dfsMineBlocks(BasicBlock &BB, SetVector<BasicBlock *> &foundBBs) {
	if (foundBBs.contains(&BB))
		return;
	foundBBs.insert(&BB);
	for (auto *suc : successors(&BB)) {
		dfsMineBlocks(*suc, foundBBs);
	}
}

// :param BB0: the top block of region, which dominates all block in
//             allBBsOfRegion exept the exit blocks :param BB: the block
// 			   for which to lower the phis

// :returns: the enable condition for a given block
Value *lowerPhisOfBlockInRegion(LowerPhisToSelectInRegionContext &ctx,
								BasicBlock &BB) {
	// PHINode *useValFromPhi = nullptr;
	// if (predsWhichWillBePreserved.size() > 1) {
	//	IRBuilderBase::InsertPointGuard g(Builder);
	//	Builder.SetInsertPoint(&exitBB, exitBB.begin());
	//	useValFromPhi = Builder.CreatePHI(Builder.getInt1Ty(),
	//			pred_size(&exitBB), "fewExitSw.useValFromPhi");
	//	for (BasicBlock *pred : predecessors(&exitBB)) {
	//		if (predsWhichWillBePreserved.contains(pred)) {
	//			useValFromPhi->addIncoming(
	//					Builder.getInt1(pred != &BBWithSwitch), pred);
	//		}
	//	}
	//	if (!is_contained(predecessors(&exitBB), &BBWithSwitch))
	//		useValFromPhi->addIncoming(Builder.getInt1(1), &BBWithSwitch);
	// }
	auto &Builder = ctx.Builder;
	auto &BB0 = ctx.BB0;
	{
		auto curEn = ctx.bbEnableCache.find(&BB);
		assert(curEn == ctx.bbEnableCache.end());
	}

	SmallVector<Value *> enFromPredecessor;
	SmallVector<bool> shouldUpdateValueForPred;
	SetVector<BasicBlock *> BBPredecessors(pred_begin(&BB), pred_end(&BB));
	bool canCompletlyRemovePhi = true;
	assert(&BB != &BB0 && "Can not remove phis in BB0 because if this is the loop the phi in header must remain");
	
	for (BasicBlock *pred : BBPredecessors) {
		if (pred != &BB0 && (ctx.bbsWhichMustPreservePhis.contains(pred) ||
							 !ctx.allBBsOfRegion.contains(pred))) {
			// :note: allBBsOfRegion has to be checked because exit block are
			// allowed to have predecessors outside of the region :note: for BB0
			// we want to perform the update if there are multiple paths in CFG
			//        from BB0 to BB not leading trough blocks in
			//        bbsWhichMustPreservePhis

			canCompletlyRemovePhi = false;
			shouldUpdateValueForPred.push_back(false);
			enFromPredecessor.push_back(nullptr);
			// for this predecessor we do not have to generate select
			// tree because we use original phi
			continue;
		}
		shouldUpdateValueForPred.push_back(true);
		// resolve condition which is 1 if the block is entered from some
		// predecessor
		Builder.SetInsertPoint(&BB0, BB0.getTerminator()->getIterator());
		auto jmpFromPredEn =
			constructBranchConditionToBBDirect(Builder, *pred, BB);

		Value *enFromPred;
		if (pred == &BB0) {
			// no need to and for en for BB0
			enFromPred = jmpFromPredEn;
		} else {
			// need to and with en for predecessor
			auto _predEn = ctx.bbEnableCache.find(pred);
			assert(_predEn != ctx.bbEnableCache.end());
			auto predEn = _predEn->second;
			enFromPred = Builder.CreateAnd(predEn, jmpFromPredEn,
										   "br." + pred->getName() + ".enFor." +
											   BB.getName());
		}
		if (auto cI = dyn_cast<Instruction>(enFromPred)) {
			if (!cI->hasName()) {
				cI->setName("fewExitSw.sucSel.en." + pred->getName());
			}
		}
		enFromPredecessor.push_back(enFromPred);
	}
	assert(enFromPredecessor.size() == BBPredecessors.size());
	assert(shouldUpdateValueForPred.size() == BBPredecessors.size());

	SmallVector<Value *> phiReplacements(llvm::range_size(BB.phis()), nullptr);
	// build a SelectInst tree from enFromPredecessor and phi operands
	for (const auto &[en, pred, shouldUpdate] :
		 zip(enFromPredecessor, BBPredecessors, shouldUpdateValueForPred)) {
		if (!shouldUpdate) {
			continue;
		}
		assert(en != nullptr);
		size_t phiIndex = 0;
		for (auto &phi : BB.phis()) {
			Value *prevVal = phiReplacements[phiIndex];
			Value *val = phi.getIncomingValueForBlock(pred);
			if (prevVal == nullptr) {
				// the case of the first pred, which we will use as a default
				phiReplacements[phiIndex] = val;
			} else {
				// all other preds
				assert(prevVal->getType() == phi.getType());
				assert(val->getType() == phi.getType());
				phiReplacements[phiIndex] =
					Builder.CreateSelect(en, val, prevVal);
			}
			phiIndex++;
		}
	}
	if (canCompletlyRemovePhi) {
		// replace phis with SelectInst
		size_t phiIndex = 0;
		for (auto &phi : make_early_inc_range(BB.phis())) {
			Value *replacement = phiReplacements[phiIndex];
			assert(replacement->getType() == phi.getType());
			replacement->takeName(&phi);
			phi.replaceAllUsesWith(replacement);
			phi.eraseFromParent();
			// assert(loweredPhiCache.find(&phi) == loweredPhiCache.end());
			// loweredPhiCache[&phi] = replacement;
			phiIndex++;
		}
	} else {
		// update incoming values for selected operands
		size_t phiIndex = 0;
		for (auto &phi : BB.phis()) {
			for (const auto &[en, pred, shouldUpdate] :
				 zip(enFromPredecessor, BBPredecessors,
					 shouldUpdateValueForPred)) {
				if (!shouldUpdate) {
					continue;
				}
				auto predI = phi.getBasicBlockIndex(pred);
				phi.setIncomingValue(predI, phiReplacements[phiIndex]);
				phi.setIncomingBlock(predI, &BB0);
			}
			++phiIndex;
		}
	}
	// delete enable for block predecessor which will be preserved
	llvm::erase_if(enFromPredecessor, [](Value *v) { return v == nullptr; });
	Value *BBEn;

	if (enFromPredecessor.empty()) {
		BBEn = nullptr; // this block is between exit blocks and have just same
						// blocks or exit blocks as predecessor
		// none of he predecessors was removed and phis were not removed or
		// updated as well the return value should never be used because this
		// block will not be removed as well
	} else {
		BBEn = Builder.CreateOr(enFromPredecessor);
	}
	ctx.bbEnableCache[&BB] = BBEn;
	return BBEn;
}

//void updatePhiOperandsBeforeCfgUpdate(LowerPhisToSelectInRegionContext &ctx) {
//	// update PHINode operands before rewrite of CFG
//	for (BasicBlock *BB : ctx.bbsWhichMustPreservePhis) {
//		SmallVector<Value *> valueFromBB0forPhisOperand(range_size(BB->phis()),
//														nullptr);
//		bool hadBB0AsPred = is_contained(predecessors(BB), &ctx.BB0);
//
//		// for each predecessor for each phi update
//		for (auto pred : predecessors(BB)) {
//			bool shouldUpdatePred =
//				BB == &ctx.BB0 || !ctx.bbsWhichMustPreservePhis.contains(pred);
//			if (!shouldUpdatePred)
//				continue; // for this blocks the value should be already up to
//						  // date
//			// replace all operands pairs for preds (which are going to
//			// be removed) with operand pair (BB0, valDefinedIn BB0),
//			// all such values should already be the same (updated in
//			// lowerPhisToSelectInRegion)
//			size_t phiIndex = 0;
//			for (auto &phi : BB->phis()) {
//				auto valForPred = phi.getIncomingValueForBlock(pred);
//				Value *valForBB0 = valueFromBB0forPhisOperand[phiIndex];
//				// :attention: If phi operand will remain and there are blocks
//				// 	between exit blocks the jump to those blocks from exit0 will
//				// disappear
//				//  and we have to emulate function of phi node tree.
//				if (hadBB0AsPred) {
//					if (!valForBB0) {
//						// lazy load
//						valForBB0 = phi.getIncomingValueForBlock(&ctx.BB0);
//						valueFromBB0forPhisOperand[phiIndex] = valForBB0;
//					} else {
//						assert(valForPred == valForBB0 &&
//							   "The operand value should have been "
//							   "updated to the same "
//							   "during lowerPhisToSelectInRegion");
//						phi.removeIncomingValue(pred,
//												/*DeletePHIIfEmpty*/ false);
//					}
//				} else {
//					phi.removeIncomingValue(pred, /*DeletePHIIfEmpty*/ false);
//					if (valForBB0) {
//						assert(valForPred == valForBB0 &&
//							   "The operand value should have been "
//							   "updated to the same "
//							   "during lowerPhisToSelectInRegion");
//					} else {
//						valForBB0 = valForPred;
//						valueFromBB0forPhisOperand[phiIndex] = valForBB0;
//						phi.addIncoming(valForBB0, &ctx.BB0);
//					}
//				}
//				++phiIndex;
//			}
//		}
//		// new UnreachableInst(suc->getContext(),
//		//		suc->getTerminator()->getIterator());
//		// suc->getTerminator()->eraseFromParent();
//	}
//}

//bool lowerPhisToSelectInRegion(LowerPhisToSelectInRegionContext &ctx) {
//
//	return true;
//}

} // namespace hwtHls