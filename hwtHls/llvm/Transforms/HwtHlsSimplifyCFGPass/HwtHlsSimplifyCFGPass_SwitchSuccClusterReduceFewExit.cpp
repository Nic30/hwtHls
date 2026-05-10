#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>

#include <cassert>
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

namespace hwtHls {

//// traverse DstBB and search for SrcBB and exit or reach of dominatingBB
// bool isPotentiallyReachableForSwitchSuccessors(BasicBlock & dominatingBB,
// BasicBlock & DstBB, BasicBlock & SrcBB) { 	if (&SrcBB == &DstBB) return
// true;
//	if (&SrcBB == &dominatingBB)
//		return false;
//	for (auto * pred: predecessors(&DstBB)) {
//		if (isPotentiallyReachableForSwitchSuccessors(dominatingBB, *pred,
// SrcBB)) 			return true;
//	}
//	return false;
// }
//

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
			//// is latch or
			// does not contain only terminator,
			// -> treat it as exit block
			exitBBs.insert(suc);
			if (exitBBs.size() > 2)
				return false; // not the pattern of interest
			continue;
		}
		if (&*suc->begin() != suc->getTerminator()) {
			// does not contain only terminator,
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
			// if (switchSuccessors.contains(sucSuc))
			//	continue; // skip because this is not exit but jump to another
			// sibling block

			// if (!uniqueExits.empty()) {
			//	if (uniqueExits.contains(sucSuc))
			//		continue; // already added
			//
			//	// in the case that the one exit dominates second it means that
			// the dominating
			//	// exit is true exit from section after switch and it has branch
			// to some other block 	SmallVector<BasicBlock*, 2>
			//_uniqueExits(uniqueExits.begin(), 			uniqueExits.end());
			// bool isDominated = false; 	for (auto curExit : _uniqueExits) {
			// if (curExit == &BB) { 		} else { 			if
			//(DT.dominates(curExit, sucSuc)) { 				isDominated =
			// true; 				break; 			} else if
			// (DT.dominates(sucSuc, curExit)) {
			// uniqueExits.remove(curExit);
			//				uniqueExits.insert(sucSuc);
			//			}
			//		}
			//	}
			//	if (isDominated)
			//		continue;
			// }
			//
			// uniqueExits.insert(sucSuc);
			// if (uniqueExits.size() > 2)
			//	return false; // not the pattern of interest
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
		return false; // this would only convert phis to select which is not
					  // considered good enough CFG simplification
		// we avoid it because it cancels the opportunity to simplify phis.
	}
	return true;
}

bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
	llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
	llvm::SwitchInst &SI, bool &exprChanged) {
	auto &BB0 = *SI.getParent();
	const SetVector<BasicBlock *> origSwitchSuccessors(succ_begin(&BB0),
													   succ_end(&BB0));
	// :attention: switchSuccessors are gathered accumulatively from all
	// dominated blocks
	SetVector<BasicBlock *> allRegionBBs(origSwitchSuccessors);
	DTU.flush();
	auto &DT = DTU.getDomTree();
	assert(DT.verify());
	SetVector<BasicBlock *> exitBBs;
	if (!HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit_matchPattern(BB0, allRegionBBs, exitBBs, DT))
		return false;
	//errs() << "uniqueExits:\n";
	//for (auto e : uniqueExits)
	//	errs() << "    " << e->getName() << "\n";
	//errs() << "before HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: "
	//	   << *BB0.getParent() << "\n";
	assert(exitBBs.size() != 0);

	// now we know that there are only <=2 unique blocks from the cluster of
	// empty blocks after the SwitchInst
	//DenseMap<BasicBlock *, Value *> bbEnableCache;
	//if (exitBBs.size() >= 2) {
	//	fewExitCluster_cutOffExitBBInClusterSuccessors(Builder, DTU, BB0,
	//												   allRegionBBs, exitBBs, bbEnableCache);
	//}
	SmallVector<DominatorTree::UpdateType> updates;
	allRegionBBs.insert(exitBBs.begin(), exitBBs.end());
	LowerPhisToSelectInRegionContext lowerPhiCtx(Builder, BB0, allRegionBBs, exitBBs);
	lowerPhiCtx.analyze();
	{
		BasicBlock::iterator bbExit1InsertBegin;
		if (lowerPhiCtx.exitBBs.size() > 1) {
			bbExit1InsertBegin = lowerPhiCtx.exitBBs[1]->getFirstInsertionPt();
			if (!lowerPhiCtx.betweenExitBBs.empty() &&
				is_contained(predecessors(lowerPhiCtx.exitBBs[1]),
							 lowerPhiCtx.exitBBs[0])) {
				// if bbExit0 is already a predecessor of bbExit1 we add
				// split edge with a new block so we can safely add new operands coming from bbExit0
				// once required
				DTU.flush();
				auto newBB =
					SplitEdge(lowerPhiCtx.exitBBs[0], lowerPhiCtx.exitBBs[1], &DTU.getDomTree());
				lowerPhiCtx.betweenExitBBs.insert(newBB);
				assert(lowerPhiCtx.allBBsOfRegion.back() ==
					   lowerPhiCtx.exitBBs[1]);
				lowerPhiCtx.allBBsOfRegion.pop_back();
				lowerPhiCtx.allBBsOfRegion.insert(newBB);
				lowerPhiCtx.allBBsOfRegion.insert(lowerPhiCtx.exitBBs[1]);
			}
		}
		// :note: lowerPhisOfBlockInRegion is required even if there are no phis, because it constructs
		//        also block enable conditions
		// :note: allBBsOfRegion are now topologically sorted so once we reach the
		// 		  block we have already seen all predecessors
		for (auto *BB : lowerPhiCtx.allBBsOfRegion) {
			if (BB == &lowerPhiCtx.BB0)
				continue; // this may happen if BB0 is also the exit block
			// errs() << "lowerPhisOfBlockInRegion: " << BB->getName() << "\n"; 
			if (lowerPhiCtx.betweenExitBBs.contains(BB) || (!lowerPhiCtx.betweenExitBBs.empty() && BB == lowerPhiCtx.exitBBs[1])) {
				// insert point will have to be set to bbExit1 because
				// some values will come from the bbExit0
				IRBuilderBase::InsertPointGuard g(Builder);
				Builder.SetInsertPoint(bbExit1InsertBegin);
				lowerPhisOfBlockInRegion(lowerPhiCtx, *BB);
			} else {
				lowerPhisOfBlockInRegion(lowerPhiCtx, *BB);
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
		//if (!lowerPhiCtx.betweenExitBBs.empty()) {
		//	exprChanged |= fewExitCluster_cutOffExitBBInClusterSuccessors(lowerPhiCtx, DTU, updates);
		//}
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
		// Input:
		//  * As input there is CFG with a region dominated by 1 block BB0 and
		//    with 2 exit(ing) blocks (BBExit0, BBExit1), all blocks in region
		//    are post dominated by BBExit0/BBExit1. Exit blocks and BB0 are
		//    allowed to have any instruction while other blocks are allowed to
		//    have only PHINodes.
		// Task:
		//  * As input there is CFG with a region dominated by 1 block BB0 and
		//    with 2 exit(ing) blocks (BBExit0, BBExit1), all blocks in region
		//    are post dominated by BBExit0/BBExit1. Exit blocks and BB0 are
		//    allowed to have any instruction while other blocks are allowed to
		//    have only PHINodes.
		// Problems:
		//  * Blocks between BBExit0/BBExit1 may also have PHINodes and we can
		//  not remove them as BBExit0 does not need to dominate BBExit1 (or in
		//  reverse).
		//    So only PHINode operands for non-exit should be lowered in this
		//    case.
		//  * It is preferred that all SelectInst are constructed in BB0 if
		//  possible.

		// :note: this does not solve the case where exit block has some other
		//        predecessors and the switch is inside of the loop
		// if (isPotentiallyReachableForSwitchSuccessors(BB, *uniqueExits[0],
		//		*uniqueExits[1])) {
		//	// swap exit block so the uniqueExits[0] dominates uniqueExits[1]
		//	auto e0 = uniqueExits[0];
		//	auto e1 = uniqueExits[1];
		//	uniqueExits.clear();
		//	uniqueExits.insert(e1);
		//	uniqueExits.insert(e0);
		//
		//	assert(
		//			!isPotentiallyReachableForSwitchSuccessors(BB,
		//					*uniqueExits[0], *uniqueExits[1])
		//					&& "There should not be any cycle");
		//}
		// switchSuccessos.remove(uniqueExits[0]);
		// switchSuccessos.remove(uniqueExits[1]);

		// DenseMap<BasicBlock *, size_t> unresolvedPredCnt;
		// for (auto *_BB : switchSuccessors) {
		//	auto predCnt = pred_size(_BB);
		//	if (uniqueExits.contains(_BB)) {
		//		for (auto predBB : predecessors(_BB)) {
		//			if (!switchSuccessors.contains(predBB)) {
		//				// ignore block which are not part of target
		//				// region because they will not change
		//				predCnt -= 1;
		//			}
		//		}
		//	}
		//	assert(predCnt > 0 && "All should have at least BB as predecessor");
		//	unresolvedPredCnt[_BB] = predCnt;
		// }
		//
		// SetVector<BasicBlock *> worklist;
		// worklist.insert(&BB);
		// while (!worklist.empty()) {
		//	auto *_BB = worklist.pop_back_val();
		// }

		//// find also all block between uniqueExits[0] and uniqueExits[1] and
		//// add them also as exit, because we can not remove them
		//// as they are part of the CFG between them (because if there is such
		//// path the def-before-use must be preserved and thus blocks between
		//// exit bbs can not be removed and path discarded)
		// SetVector<BasicBlock *> worklist(uniqueExits);
		// while (!worklist.empty()) {
		//	auto sucBB = worklist.pop_back_val();
		//	for (auto sucSucBB : successors(sucBB)) {
		//		if (!switchSuccessors.contains(sucSucBB)) {
		//			uniqueExits.insert(sucSucBB);
		//			worklist.insert(sucSucBB);
		//		}
		//	}
		// }

		// exprChanged = true;
		//// lower phis in blocks which will be removed
		//// this should assert that nothing used in
		// for (auto *newSuc : uniqueExits) {
		//	if (newSuc->phis().empty())
		//		continue;
		//	if (all_of(predecessors(newSuc), [&uniqueExits](BasicBlock *pred) {
		//			return uniqueExits.contains(pred);
		//		})) {
		//		// no need because all phi operands will stay
		//		continue;
		//	}
		//	lowerPhisToSelect(Builder, BB, switchSuccessors, uniqueExits,
		//					  *newSuc, bbEnableCache, loweredPhiCache);
		// }
		//  must be constructed before we remove terminator from pred blocks
		assert(Builder.GetInsertPoint() == SI.getIterator());
		if (exitBBs[0] == &BB0) {
			assert(lowerPhiCtx.bbEnableCache.contains(exitBBs[1]));
			auto toExit1brCond = lowerPhiCtx.bbEnableCache[exitBBs[1]];
			assert(toExit1brCond);
			Builder.CreateCondBr(toExit1brCond, exitBBs[1], exitBBs[0]);
		} else {
			assert(lowerPhiCtx.bbEnableCache.contains(exitBBs[0]));
			auto toExit0brCond = lowerPhiCtx.bbEnableCache[exitBBs[0]];
			assert(toExit0brCond);
			Builder.CreateCondBr(toExit0brCond, exitBBs[0], exitBBs[1]);
		}
		
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
			auto sucPreserved = lowerPhiCtx.bbsWhichMustPreservePhis.contains(sucBB);
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

	DTU.applyUpdates(updates);
	//DTU.flush();
	for (auto *eBB : exitBBs) {
		sortPhiOperands(*eBB, /*removeRedundantOperands*/ true);
	}
	//errs() << "after HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit: "
	//		<< *BB0.getParent() << "\n";

	return true;
}

} // namespace hwtHls
