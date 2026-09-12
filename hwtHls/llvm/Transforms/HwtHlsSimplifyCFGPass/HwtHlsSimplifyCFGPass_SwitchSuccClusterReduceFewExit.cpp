#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.h>

#include <cassert>

#include <llvm/ADT/iterator_range.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/LoopInfo.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/CFG.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

//#define SwitchSuccClusterReduceFewExit_TRACE
#ifdef SwitchSuccClusterReduceFewExit_TRACE
#include <llvm/IR/Verifier.h>
#endif

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_matchPattern(
	BasicBlock &BB0, SetVector<BasicBlock *> &allRegionBBs,
	SetVector<BasicBlock *> &exitBBs, DominatorTree &DT) {
	// :note: BB0 is in allRegionBBs if it is a loop header and latches were
	// also added in allRegionBBs (the loop body is beeing transformed by this opt.)
	//auto& EntryBB = BB0.getParent()->getEntryBlock();
	//LoopInfo LI(DT);
	for (size_t i = 0; i < allRegionBBs.size(); ++i) {
		BasicBlock *suc = allRegionBBs[i];
		assert(!pred_empty(suc));
		// auto L = LI.getLoopFor(suc);
		// L->getParentLoop()
		
		//if (!DT.dominates(&EntryBB, suc)) {
		//	// some predecessor is unreachable
		//	return false;
		//} 
		if (&BB0 == suc ||
			!DT.dominates(&BB0, suc) || // is successor
			any_of(predecessors(suc), [&allRegionBBs, &BB0](BasicBlock * BB) {
				// this check is to cover for blocks which may have unreachable predecessors
				return BB != &BB0 && !allRegionBBs.contains(BB);
			})
			//|| is_contained(successors(suc), &BB)
		) {
			// is entered from somewhere else than after switch region or
			//// is latch or does not contain only terminator,
			// -> treat it as exit block
			exitBBs.insert(suc);
			if (exitBBs.size() > 2)
				return false; // not the pattern of interest
			continue;
		}
		if (&*suc->begin() != suc->getTerminator()) {
			// does not contain just the terminator,
			// -> treat it as exit block
			if (!tryHoistCheapInstsAtBlockBegin(
					*suc, BB0.getTerminator()->getIterator()) ||
				&*suc->begin() != suc->getTerminator()) {
				// hoist is not possible
				exitBBs.insert(suc);
				if (exitBBs.size() > 2)
					return false; // not the pattern of interest
				continue;
			}
		}

		auto t = suc->getTerminator();
		if (isa<UnreachableInst>(t)) {
			continue; // this block is irrelevant during search of exits as it
					  // can not be reached
		} else if (!isa<BranchInst>(t) && !isa<SwitchInst>(t)) {
			// unsupported terminator
			return false;
		}

		for (auto sucSuc : successors(suc)) {
			allRegionBBs.insert(sucSuc);
		}
	}
	if (allRegionBBs.size() == exitBBs.size() &&
		all_of(exitBBs, [&allRegionBBs](BasicBlock *eBB) {
			return allRegionBBs.contains(eBB);
		}))
		return false; // there are no blocks to reduce, all successors are exit
					  // blocks

	// if (uniqueExits.size() > 1 && uniqueExits.contains(&BB))
	//	return false; // for now we can not allow that because the other exit
	// block would not receive correct predecessors
	if (exitBBs.size() == 1 && succ_size(&BB0) == allRegionBBs.size() &&
		all_of(allRegionBBs, [](BasicBlock *caseBB) {
			auto t = caseBB->getTerminator();
			if (auto br = dyn_cast<BranchInst>(t)) {
				return !br->isConditional();
			} else if (isa<UnreachableInst>(t)) {
				return false;
			} else {
				return true;
			}
		})) {
		// this would only convert phis to select which is not
  	    // considered good enough CFG simplification
		// we avoid it because it cancels the opportunity to simplify phis.
		return false;
	}

	return true;
}

static void cleanupBlockWhichBecomeUnreachable(
	LowerPhisToSelectInRegionContext &lowerPhiCtx,
	const SetVector<BasicBlock *>& blocks,
	SmallVector<DominatorTree::UpdateType>& updates) {
	/// change terminator to UnreachableInst for dangling unreachable blocks
	/// without predecessor after we rerouted the parent SwitchInst
	SetVector<BasicBlock *> worklist;
	// init worklist
	for (auto *BB : blocks) {
		if (pred_empty(BB)) {
			worklist.insert(BB);
		}
	}
	while (!worklist.empty()) {
		BasicBlock *BB = worklist.pop_back_val();
		assert(!lowerPhiCtx.bbsWhichMustPreservePhis.contains(BB));
		auto term = BB->getTerminator();
		SetVector<BasicBlock *> bbSuccessors(succ_begin(BB), succ_end(BB));
		// :note: remove in advance to avoid problems with SwitchInst which may
		// have BB as successor multipletimes
		if (!isa<UnreachableInst>(term)) {
			new UnreachableInst(BB->getContext(), term->getIterator());
			term->eraseFromParent();
		}
		assert(BB->phis().empty() && "Phis for blocks which are going to be "
									 "removed should be already lowered");
		BB->moveBefore(BB->getParent()->end());
		for (auto sucBB : bbSuccessors) {
			// BB block is now unreachable, from this reason we has to
			// replace all successor phi values for this BB with PoisonValue to
			// prevent use before def, the value of phi in successor should be
			// already updated and the incoming value from BBWithSwitch should
			// have the value as this value had before this transformation
			auto sucPreserved =
				lowerPhiCtx.bbsWhichMustPreservePhis.contains(sucBB);
			if (!sucPreserved) {
				assert(sucBB->phis().empty() &&
					   "Phis for blocks which are going to be removed should "
					   "be already lowered");
			}
			// for (auto& phi: sucBB->phis()) {
			// 	phi.removeIncomingValue(BB, false);
			// }
			if (pred_empty(sucBB)) {
				worklist.insert(sucBB);
			}
			updates.push_back({DominatorTree::Delete, BB, sucBB});
		}
	}
}

// The exit from section can not be the header of the loop, it must be replaced
// with a latch, and it is optionally required to construct this latch if
// it does not exit.
static bool
HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_form_dedicatedLatches(
	llvm::DomTreeUpdater &DTU, BasicBlock &BB0,
	SetVector<BasicBlock *> &origSwitchSuccessors,
	SetVector<BasicBlock *> &allRegionBBs, SetVector<BasicBlock *> &exitBBs) {
	bool change = false;
	if (exitBBs.size() == 1)
		return change;
	auto &DT = DTU.getDomTree();
	for (auto * exitBB: exitBBs) {
		SmallVector<BasicBlock *> inRegionExitLatches;
		for (auto pred : predecessors(exitBB)) {
			if (DT.dominates(exitBB, pred)) {
				// [todo] move loop metadata from predecessor, because we
				// creating a new latch
				inRegionExitLatches.push_back(pred);
			}
		}
		if (inRegionExitLatches.empty()) {
			// exitBB not a header of the loop
			continue;
		}
		bool allNonExitsDominatedByExitBB = true;
		for (auto BB: allRegionBBs) {
			if (!DT.dominates(exitBB, BB)) {
				allNonExitsDominatedByExitBB = false;
				break;
			}
		}
		if (!allNonExitsDominatedByExitBB) {
			// the loop on exitBB is situated after the section
			continue;
		} else {
			// the section is contained within the loop with exitBB as header 
		}
		
		BasicBlock *newExit;
		if (inRegionExitLatches.size() == 1 && inRegionExitLatches[0] != exitBB) {
			// use existing latch
			newExit = inRegionExitLatches[0];
		} else {
			auto *MD = inRegionExitLatches[0]->getTerminator()->getMetadata(LLVMContext::MD_loop);
			newExit = SplitBlockPredecessors(exitBB, inRegionExitLatches,
											 ".ExitLatch", &DTU);
			newExit->getTerminator()->setMetadata(LLVMContext::MD_loop, MD);
			for (auto pred : inRegionExitLatches) {
				pred->getTerminator()->setMetadata(LLVMContext::MD_loop, nullptr);
			}								 
			change = true;
		}

#ifdef SwitchSuccClusterReduceFewExit_TRACE
		errs() << "HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_form_dedicatedLatches: ";
		exitBB->printAsOperand(errs());
		errs() << " -> ";
		newExit->printAsOperand(errs());
		errs() << "\n";
#endif
		allRegionBBs.insert(newExit);
		if (exitBB == &BB0) {
			origSwitchSuccessors.remove_if(
				[&BB0](BasicBlock *BB) { return BB == &BB0; });
			origSwitchSuccessors.insert(newExit);
		} else {
			allRegionBBs.remove(exitBB);
		}
		// substitute BB0 exit with a newExit
		if (exitBBs[0] == exitBB) {
			auto e1 = exitBBs.pop_back_val();
			exitBBs.pop_back();
			exitBBs.insert(newExit);
			exitBBs.insert(e1);
		} else {
			exitBBs.pop_back();
			exitBBs.insert(newExit);
		}
		DTU.flush();
	}
	return change;
}


bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_lowerPhis(LowerPhisToSelectInRegionContext& lowerPhiCtx, llvm::IRBuilderBase &Builder) {
	// :note: lowerPhisOfBlockInRegion is required even if there are no phis, because it constructs
	//        also block enable conditions
	// :note: allBBsOfRegion are now topologically sorted so once we reach the
	// 		  block we have already seen all predecessors
	// errs() << "BB0: ";
	// lowerPhiCtx.BB0.printAsOperand(errs());
	// errs() << "\n";
	bool exprChanged = false;
	auto &BB0 = lowerPhiCtx.BB0;
	//SetVector<BasicBlock*> preservedPredecessors;
	//preservedPredecessors.insert_range(lowerPhiCtx.betweenExitBBs);
	//preservedPredecessors.insert_range(lowerPhiCtx.exitBBs);
	for (auto *BB : lowerPhiCtx.allBBsOfRegion) {
		if (BB == &lowerPhiCtx.BB0)
			continue; // this may happen if BB0 is also the exit block
		// if (lowerPhiCtx.bbsWhichMustPreservePhis.contains(BB))
		// 	continue;

#ifdef SwitchSuccClusterReduceFewExit_TRACE
		errs() << "lowerPhisOfBlockInRegion: ";
		BB->printAsOperand(errs());
		errs() << "\n";
#endif
		lowerPhisOfBlockInRegion(lowerPhiCtx, *BB);
		exprChanged |= !BB->phis().empty(); 
	}
	// for BB0 update phi incoming blocks to be BB0 for removed blocks
	if (lowerPhiCtx.allBBsOfRegion.contains(&BB0)) {
		for (auto &phi : BB0.phis()) {
			for (unsigned i = 0; i < phi.getNumIncomingValues(); ++i) {
				auto pred = phi.getIncomingBlock(i);
				if (pred != &BB0 && lowerPhiCtx.allBBsOfRegion.contains(pred) &&
					!lowerPhiCtx.bbsWhichMustPreservePhis.contains(pred)) {
					phi.setIncomingBlock(i, &BB0);
				}
			}
		}
	}
	return exprChanged;
}

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
	llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
	llvm::SwitchInst &SI, bool &exprChanged) {
	auto &BB0 = *SI.getParent();
	DTU.flush();
	auto &DT = DTU.getDomTree();
	// assert(DT.verify());

#ifdef SwitchSuccClusterReduceFewExit_TRACE
	assert(!verifyFunction(*BB0.getParent(), &errs()));
	assert(DTU.getDomTree().verify());
#endif
	SetVector<BasicBlock *> origSwitchSuccessors(succ_begin(&BB0),
  											     succ_end(&BB0));
	// :attention: switchSuccessors are gathered accumulatively from all
	// dominated blocks
	SetVector<BasicBlock *> allRegionBBs(origSwitchSuccessors);
	SetVector<BasicBlock *> exitBBs;
	if (!HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_matchPattern(BB0, allRegionBBs, exitBBs, DT))
		return false;
	bool change = false;
	change |= HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_form_dedicatedLatches(
		DTU, BB0, origSwitchSuccessors, allRegionBBs, exitBBs);
	if (exitBBs.size() == 2 && exitBBs.contains(&BB0)) {
		// This is required because IP for select/phis would not be clearly defined
		return change;
	}

#ifdef SwitchSuccClusterReduceFewExit_TRACE
	errs() << "before HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: \n"
		   << *BB0.getParent() << "\n";
#endif
	assert(exitBBs.size() != 0);
	// now we know that there are only <=2 unique blocks from the cluster of
	// empty blocks after the SwitchInst
	allRegionBBs.insert(exitBBs.begin(), exitBBs.end());
	LowerPhisToSelectInRegionContext lowerPhiCtx(Builder, BB0, allRegionBBs, exitBBs);
	if (!lowerPhiCtx.analyze()) {
		return change;
	}
	if (all_of(lowerPhiCtx.allBBsOfRegion, [&lowerPhiCtx](BasicBlock *BB) {
		return &lowerPhiCtx.BB0 == BB || lowerPhiCtx.exitBBs.contains(BB);
	})) {
		return change; // too simple CFG for this transformation
	}
#ifdef SwitchSuccClusterReduceFewExit_TRACE
	errs() << lowerPhiCtx << "\n"; 
#endif
	//if (!lowerPhiCtx.blocksReachableFromBB0WithoutExit0.empty()) {
	if (exitBBs.size() > 1) {
		change |= lowerPhiCtx.blocksReachableFromBB0WithoutExit0_unswitch(DTU, origSwitchSuccessors);
	#ifdef SwitchSuccClusterReduceFewExit_TRACE
		errs() << "HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit after blocksReachableFromBB0WithoutExit0_unswitch: \n";
		BB0.getParent()->dump();
		assert(!verifyFunction(*BB0.getParent(), &errs()));
		assert(DTU.getDomTree().verify());
	#endif
	}
	change |= lowerPhiCtx.unreachableExits_unswitch(DTU, origSwitchSuccessors);
	DTU.flush();
	lowerPhiCtx.bbsWhichMustPreservePhis.insert_range(lowerPhiCtx.betweenExitBBs);

	{
		lowerPhiCtx.bb0SelectInsertPos = BB0.getTerminator()->getIterator();
		//lowerPhiCtx.bbExit0SelectInsertPos = lowerPhiCtx.exitBBs[0]->getFirstInsertionPt();
		//if (lowerPhiCtx.exitBBs.size() > 1) {
		//	lowerPhiCtx.bbExit1SelectInsertPos = lowerPhiCtx.exitBBs[1]->getFirstInsertionPt();
		//}
#ifdef SwitchSuccClusterReduceFewExit_TRACE
		errs() << "HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit\n";
		errs() << lowerPhiCtx;
#endif
		exprChanged |= HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_lowerPhis(lowerPhiCtx, Builder);
	} // else no phis to lower

	SmallVector<DominatorTree::UpdateType> updates;
	for (BasicBlock *BB : origSwitchSuccessors) {
		if (lowerPhiCtx.bbsWhichMustPreservePhis.contains(BB))
			continue;
		updates.push_back({DominatorTree::Delete, &BB0, BB});
	}
	for (BasicBlock *BB : lowerPhiCtx.exitBBs) {
		// if there is a path from BB0 to BB which does not contain any exitBB
		if (!any_of(exitBBs, [&DT, BB](BasicBlock *eBB) {
				// :note: if properly dominates it means that
				// 		the BB is somewhere between exitBBs blocks
				//      and removing blocks will not result in branch from BB0
				//      to this block
				return DT.properlyDominates(eBB, BB);
			}))
			continue; // BB0 -> BB will not be added
		if (!is_contained(successors(&BB0), BB)) {
			updates.push_back({DominatorTree::Insert, &BB0, BB});
		}
	}
	// [fixme] preserve metadata
	Builder.SetInsertPoint(&SI);
	switch (exitBBs.size()) {
	case 0: {
		Builder.CreateUnreachable();
		SI.eraseFromParent();
		break;
	}
	case 1: {
		Builder.CreateBr(exitBBs[0]);
		SI.eraseFromParent();
		break;
	}
	case 2: {
		//  must be constructed before we remove terminator from pred blocks
		assert(Builder.GetInsertPoint() == SI.getIterator());
		assert(exitBBs[0] != &BB0);
		assert(lowerPhiCtx.bbEnableCache.contains(exitBBs[0]));
		Value * toExit0brCond = lowerPhiCtx.bbEnableCache[exitBBs[0]];
		assert(toExit0brCond);
		Builder.CreateCondBr(toExit0brCond, exitBBs[0], exitBBs[1]);
		
		for (auto newSuc : exitBBs) {
			if (!origSwitchSuccessors.contains(newSuc)) {
				updates.push_back({DominatorTree::Insert, &BB0, newSuc});
			}
		}
		SI.eraseFromParent();
		break;
	}
	default:
		llvm_unreachable("All cases should be already handled");
	}
	// SetVector<BasicBlock *> potentiallyUnreachableBlocks;
	// potentiallyUnreachableBlocks.insert_range(origSwitchSuccessors);
	// potentiallyUnreachableBlocks.insert_range(lowerPhiCtx.betweenExitBBs);
	DTU.applyUpdates(updates);
	DTU.flush();
	updates.clear();
	cleanupBlockWhichBecomeUnreachable(lowerPhiCtx, origSwitchSuccessors,
									   updates);

	DTU.applyUpdates(updates);
	DTU.flush();
	for (auto *eBB : exitBBs) {
		sortPhiOperands(*eBB, /*removeRedundantOperands*/ true, /*addForDuplicatedPredecessors*/ true);
	}
#ifdef SwitchSuccClusterReduceFewExit_TRACE
	errs() << "after HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: \n"
			<< *BB0.getParent() << "\n";
	assert(!verifyFunction(*BB0.getParent(), &errs()));
	assert(DTU.getDomTree().verify());
#endif
			
	return true;
}

} // namespace hwtHls
