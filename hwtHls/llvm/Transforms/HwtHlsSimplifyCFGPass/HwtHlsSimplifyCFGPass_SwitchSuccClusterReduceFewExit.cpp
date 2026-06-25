#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>

#include <cassert>
#include <llvm-21/llvm/IR/LLVMContext.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>
#include <llvm/IR/Dominators.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/CFG.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>

#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>

using namespace llvm;

// #define TRACE_SwitchSuccClusterReduceFewExit

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_matchPattern(
	BasicBlock &BB0, SetVector<BasicBlock *> &allRegionBBs,
	SetVector<BasicBlock *> &exitBBs, DominatorTree &DT) {
	for (size_t i = 0; i < allRegionBBs.size(); ++i) {
		BasicBlock *suc = allRegionBBs[i];
		// is successor
		if (&BB0 == suc || !DT.dominates(&BB0, suc)
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
	const SetVector<BasicBlock *>& origSwitchSuccessors,
	SmallVector<DominatorTree::UpdateType>& updates) {
	/// change terminator to UnreachableInst for dangling unreachable blocks
	/// without predecessor after we rerouted the parent SwitchInst
	SetVector<BasicBlock *> worklist;
	// init worklist
	for (auto *BB : origSwitchSuccessors) {
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
		if (inRegionExitLatches.empty())
			continue;
		BasicBlock *newExit;
		if (inRegionExitLatches.size() == 1 && inRegionExitLatches[0] != exitBB) {
			// use existing latch
			newExit = inRegionExitLatches[0];
		} else {
			auto *MD = inRegionExitLatches[0]->getTerminator()->getMetadata(LLVMContext::MD_loop);
			newExit = SplitBlockPredecessors(exitBB, inRegionExitLatches,
											 ".BB0Split", &DTU);
			newExit->getTerminator()->setMetadata(LLVMContext::MD_loop, MD);
			for (auto pred : predecessors(exitBB)) {
				pred->getTerminator()->setMetadata(LLVMContext::MD_loop, nullptr);
			}								 
			change = true;
		}
		allRegionBBs.insert(newExit);
		if (exitBB == &BB0) {
			origSwitchSuccessors.remove_if(
				[&BB0](BasicBlock *BB) { return BB == &BB0; });
			origSwitchSuccessors.insert(newExit);
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

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
	llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
	llvm::SwitchInst &SI, bool &exprChanged) {
	auto &BB0 = *SI.getParent();
	DTU.flush();
	auto &DT = DTU.getDomTree();
	// assert(DT.verify());
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
	assert(exitBBs.size() != 0);
	// now we know that there are only <=2 unique blocks from the cluster of
	// empty blocks after the SwitchInst
	SmallVector<DominatorTree::UpdateType> updates;
	allRegionBBs.insert(exitBBs.begin(), exitBBs.end());
	LowerPhisToSelectInRegionContext lowerPhiCtx(Builder, BB0, allRegionBBs, exitBBs);
	lowerPhiCtx.analyze();
	if (all_of(lowerPhiCtx.allBBsOfRegion, [&lowerPhiCtx](BasicBlock *BB) {
		return &lowerPhiCtx.BB0 == BB || lowerPhiCtx.exitBBs.contains(BB);
	})) {
		return change; // too simple CFG for this transformation
	}
#ifdef TRACE_SwitchSuccClusterReduceFewExit
	errs() << "before HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: \n"
		   << *BB0.getParent() << "\n";
#endif
	{
		lowerPhiCtx.bb0SelectInsertPos = BB0.getTerminator()->getIterator();
		if (lowerPhiCtx.exitBBs.size() > 1) {
			lowerPhiCtx.bbExit1SelectInsertPos = lowerPhiCtx.exitBBs[1]->getFirstInsertionPt();
		}
#ifdef TRACE_SwitchSuccClusterReduceFewExit
		errs() << "HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit\n";
		errs() << "bb0:";
		BB0.printAsOperand(errs());
		errs() << "\n";
		errs() << "allBBsOfRegion:\n";
		for (auto bb : lowerPhiCtx.allBBsOfRegion) {
			errs() << "    ";
			bb->printAsOperand(errs());
			errs() << "\n";
		}
		errs() << "blocksReachableFromBB0WithoutExit0:\n";
		for (auto bb : lowerPhiCtx.blocksReachableFromBB0WithoutExit0) {
			errs() << "    ";
			bb->printAsOperand(errs());
			errs() << "\n";
		}
		errs() << "betweenExitBBs:\n";
		for (auto bb : lowerPhiCtx.betweenExitBBs) {
			errs() << "    ";
			bb->printAsOperand(errs());
			errs() << "\n";
		}
		errs() << "exits:\n";
		for (auto e : lowerPhiCtx.exitBBs) {
			errs() << "    ";
			e->printAsOperand(errs());
			errs() << "\n";
		}
#endif
		
		// :note: lowerPhisOfBlockInRegion is required even if there are no phis, because it constructs
		//        also block enable conditions
		// :note: allBBsOfRegion are now topologically sorted so once we reach the
		// 		  block we have already seen all predecessors
		// errs() << "BB0: ";
		// lowerPhiCtx.BB0.printAsOperand(errs());
		// errs() << "\n";
		for (auto *BB : lowerPhiCtx.allBBsOfRegion) {
			if (BB == &lowerPhiCtx.BB0)
				continue; // this may happen if BB0 is also the exit block
			// if (lowerPhiCtx.bbsWhichMustPreservePhis.contains(BB))
			// 	continue;
			// errs() << "lowerPhisOfBlockInRegion: ";
			// BB->printAsOperand(errs());
			// errs() << "\n";
			if (lowerPhiCtx.betweenExitBBs.contains(BB) ||
				(!lowerPhiCtx.betweenExitBBs.empty() &&
				 BB == lowerPhiCtx.exitBBs[1])) {
				assert( lowerPhiCtx.exitBBs.size() == 2);
				// insert point will have to be set to bbExit1 because
				// some values will come from the bbExit0
				Builder.SetInsertPoint(lowerPhiCtx.bbExit1SelectInsertPos);
				// construct select only for incoming values from the {allBBsOfRegion - betweenExitBBs}, keep rest as is
				// do not update uses
				lowerPhisOfBlockInRegion(lowerPhiCtx, *BB, true);
			} else {
				Builder.SetInsertPoint(lowerPhiCtx.bb0SelectInsertPos);
				lowerPhisOfBlockInRegion(lowerPhiCtx, *BB, false);
			}
			exprChanged |= !BB->phis().empty(); 
		}
		// for BB0 update phi incoming blocks to be BB0 for removed blocks
		if (lowerPhiCtx.allBBsOfRegion.contains(&BB0)) {
			for (auto &phi : BB0.phis()) {
				for (unsigned i = 0; i < phi.getNumIncomingValues(); ++i) {
					auto pred = phi.getIncomingBlock(i);
					if (pred != &BB0 &&
						lowerPhiCtx.allBBsOfRegion.contains(pred) &&
						!lowerPhiCtx.bbsWhichMustPreservePhis.contains(pred)) {
						phi.setIncomingBlock(i, &BB0);
					}
				}
			}
		}
	} // else no phis to lower
	for (BasicBlock *BB : origSwitchSuccessors) {
		if (lowerPhiCtx.bbsWhichMustPreservePhis.contains(BB))
			continue;
		updates.push_back({DominatorTree::Delete, &BB0, BB});
	}
	for (BasicBlock *BB : lowerPhiCtx.bbsWhichMustPreservePhis) {
		// if there is a path from BB0 to BB which does not contain any exitBB
		if (!any_of(exitBBs, [&DT, BB](BasicBlock *eBB) {
				// :note: if properly dominates it means that
				// 		the BB is somewhere between uniqueExits blocks
				//      and removing blocks will not result in branch from BB0
				//      to this block
				return DT.properlyDominates(eBB, BB);
			}))
			continue; // BB0 -> BB will not be added
		if (!is_contained(successors(&BB0), BB)) {
			updates.push_back({DominatorTree::Insert, &BB0, BB});
		}
	}

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

		DTU.applyUpdates(updates);
		DTU.flush();
		updates.clear();
		break;
	}
	default:
		llvm_unreachable("All cases should be already handled");
	}

	cleanupBlockWhichBecomeUnreachable(lowerPhiCtx, origSwitchSuccessors,
									   updates);

	DTU.applyUpdates(updates);
	DTU.flush();
	for (auto *eBB : exitBBs) {
		sortPhiOperands(*eBB, /*removeRedundantOperands*/ true);
	}
#ifdef TRACE_SwitchSuccClusterReduceFewExit
	errs() << "after HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: \n"
			<< *BB0.getParent() << "\n";
	assert(!verifyFunction(*BB0.getParent(), &errs()));
#endif
			
	return true;
}

} // namespace hwtHls
