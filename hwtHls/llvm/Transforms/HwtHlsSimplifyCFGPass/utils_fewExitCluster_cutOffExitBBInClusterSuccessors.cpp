#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_fewExitCluster_cutOffExitBBInClusterSuccessors.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>

#include <queue>
#include <cassert>

#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SmallPtrSet.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/Analysis/InstructionSimplify.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/Dominators.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Support/ErrorHandling.h>

using namespace llvm;

namespace hwtHls {

void findBlocksBetweenExitBlocksOfRegion(
	const BasicBlock& BB0,
	const SetVector<BasicBlock *> &allRegionBBs,
	const SetVector<BasicBlock *> &exitBBs,
	SetVector<BasicBlock *> &betweenExitBBs) {
	SmallVector<BasicBlock *> worklist;
	for (auto eBB : exitBBs) {
		for (auto *Succ : successors(eBB)) {
			if (Succ != &BB0 && !exitBBs.contains(Succ) && allRegionBBs.contains(Succ))
				worklist.push_back(Succ);
		}
	}

	while (!worklist.empty()) {
		auto *Cur = worklist.pop_back_val();
		if (betweenExitBBs.contains(Cur))
			continue;

		betweenExitBBs.insert(Cur);
		for (auto *Succ : successors(Cur)) {
			if (Succ != &BB0 && !exitBBs.contains(Succ) && allRegionBBs.contains(Succ) &&
				!betweenExitBBs.contains(Succ))
				worklist.push_back(Succ);
		}
	}
}

void topologicalSortForBlocks(SetVector<BasicBlock *> &blocks,
							  BasicBlock *BB0) {
	if (blocks.empty())
		return;
	SetVector<BasicBlock *> blocksTmp;
	std::unordered_map<BasicBlock *, int> unseenPredCnt;
	std::queue<BasicBlock *> ready;

	// dbgs() << "topologicalSortForBlocks:\n";
	bool BB0WasInBlocks = BB0 && !blocks.insert(BB0);
	// dbgs() << "BB0: ";
	// BB0->printAsOperand(dbgs());
	// dbgs() << "\n";
	DenseSet<std::pair<BasicBlock *, BasicBlock *>>
		ignoredEdges; // backedge in potential loop BB1->BB2, BB2->BB1
	for (auto *BB : blocks) {
		int indeg = 0;

		// dbgs() << "BB: ";
		// BB->printAsOperand(dbgs());
		// dbgs() << "\n";

		for (auto *pred : predecessors(BB)) {
			if (BB == pred) {
				// ignore reflexive edges
			} else if (blocks.contains(pred)) {
				// dbgs() << "  pred: ";
				// pred->printAsOperand(dbgs());
				// dbgs() << "\n";
				if (is_contained(successors(BB), pred)) {
					// loop BB1->BB2, BB2->BB1
					if (ignoredEdges.contains({pred, BB})) {
					} else {
						if (BB0 && pred == BB0) {
							// dbgs() << "ignore0: ";
							// BB->printAsOperand(dbgs());
							// dbgs() << " -> ";
							// pred->printAsOperand(dbgs());
							// dbgs() << "\n";
							ignoredEdges.insert({BB, pred});
							indeg++;
						} else if (BB0 && BB == BB0) {
							// dbgs() << "ignore1: ";
							// pred->printAsOperand(dbgs());
							// dbgs() << " -> ";
							// BB->printAsOperand(dbgs());
							// dbgs() << "\n";
							ignoredEdges.insert({pred, BB});
						} else {
							// ignore both edges and let other edges to decide
							// the order
							dbgs() << "ignore2: ";
							pred->printAsOperand(dbgs());
							dbgs() << " <-> ";
							BB->printAsOperand(dbgs());
							dbgs() << "\n";
							ignoredEdges.insert({pred, BB});
							ignoredEdges.insert({BB, pred});
						}
					}
				} else {
					indeg++;
				}
			}
		}
		if (BB0 && BB == BB0) {
			indeg = 0;
		}
		// dbgs() << " " << indeg << "\n";
		unseenPredCnt[BB] = indeg;

		if (indeg == 0) {
			ready.push(BB);
		}
	}
	assert(!ready.empty() && "Blocks are 1 cycle and BB0 was not specified");
	while (!ready.empty()) {
		auto *BB = ready.front();
		ready.pop();
		if (BB != BB0 || BB0WasInBlocks)
			blocksTmp.insert(BB);

		// dbgs() << "ready BB: ";
		// BB->printAsOperand(dbgs());
		// dbgs() << "\n";
		for (auto sucBB : successors(BB)) {
			if (sucBB == BB || (BB0 && sucBB == BB0) || !blocks.contains(sucBB) ||
				ignoredEdges.contains({BB, sucBB})) {
				// skip self-loops, loop backedges and blocks outside of region
				continue;
			}
			// dbgs() << "  sucBB: ";
			// sucBB->printAsOperand(dbgs());
			// dbgs() << "\n";
			assert(unseenPredCnt[sucBB] > 0);
			if (--unseenPredCnt[sucBB] == 0) {
				ready.push(sucBB);
			}
		}
	}
#ifndef NDEBUG
	for (auto unseen : unseenPredCnt) {
		if (unseen.second != 0) {
			unseen.first->printAsOperand(errs());
			errs() << "\n";
			llvm_unreachable("topologicalSortForBlocks: block order was not "
							 "resolved correctly");
		}
	}
#endif
	blocks = blocksTmp;
}

//bool fewExitCluster_cutOffExitBBInClusterSuccessors(
//		LowerPhisToSelectInRegionContext& lowerPhiCtx,
//		llvm::DomTreeUpdater &DTU,
//		SmallVector<DominatorTree::UpdateType>& updates) {
//	// This function receives a region of code represented using allRegionBBs.
//	//  * BB0 dominates all blocks in the region except exitBBs and blocks
//	//    which may be placed between them.
//	//  * There are exactly 2 items in exitBBs
//	//    (and they are topologically sorted, exitBBs[0] being transitive
//	//    predecessor of exitBBs[1]).
//	//  * All blocks in region except for exitBBs and blocks betweenExitBBs
//	//    contain only PHINodes and terminators. betweenExitBBs in addition
//	//    can contain SelectInst and logical operators.
//	// This function disconnect successors of exitBBs[0] which are in
//	// allRegionBBs and replaces them with jump to exitBBs[1]. Phis operands
//	// will be updated. Some part of phis will be lowered to SelectInst. The
//	// phis in exitBBs[1] have to be replaced with a combination of phi and
//	// SelectInst to emulate behavior of the phis in blocks in region.
//	assert(lowerPhiCtx.exitBBs.size() == 2);
//
//	// 1. localize blocks between exits
//
//	// :note: all values defined in exitBB0 and used in any
//	// betweenExitBBs/exitBB1 must have
//	//   phi in exitBB1
//
//	// :problem: betweenExitBBs blocks may contain blocks dominated and
//	// non-dominated by exitBB0.
//	//           betweenExitBBs branch conditions may also be driven by phis
//	//           which are merging defs from exitBB0 and other blocks of the
//	//           cluster. This implies that the branch condition for a
//	//           betweenExitBBs may not be movable to BB0 or exitBB0 end. And in
//	//           some cases we need to construct at exitBB1 begin.
//
//	// :note: problem is how to preserve use after def,
//	//        phis in blocks are for a reason and we can not simply replace it
//	//        by SelectInst with br cond in all successors
//
//	// :note: Eventually all instructions can be moved to BB0 end or exitBBs[0]
//	// end or exitBBs[1] begin
//	// * BB0 end if value def transitively in region resides in blocks dominated
//	// by BB0 but not between exitBBs
//	// * exitBBs[0] end if def transitively in region have instruction in
//	// exitBBs[0] and
//	//   all defs are dominated by exitBBs[0] (no merge-in path transitively
//	//   from BB0)
//	// * exitBBs[1] begin if def transitively in region have instruction in
//	// blocks between exitBBs
//
//	// :note: SelectInst and its conditions has to be checked for def location
//	// and PHINode has to be created in exitBBs[1] if defs from exitBBs[0] and
//	// any other block are mixed
//
//	// 2. iteratively construct enable flags for every branch in the cluster
//	auto & exitBBs = lowerPhiCtx.exitBBs;
//	auto & betweenExitBBs = lowerPhiCtx.betweenExitBBs;
//	const SetVector<BasicBlock *> exitBB0Successors(succ_begin(exitBBs[1]),
//													succ_end(exitBBs[1]));
//	// It is necessary to lower full phi tree to select tree in exitBBs[0] for
//	// all branches from exitBBs[0] because we need to also preserve the order
//	// in which the selection was performed. That would not be possible for
//	// example if we lower only expressions dependent on exitBBs[0] and then
//	// merge with a value from reduced phi tree.
//
//	// :note: at the end the exitBBs[1] will contain phis which will select
//	// between original values form
//	//  betweenExitBBs/allRegionBBs and a value from exitBBs[0] which will be a
//	//  select tree emulating the phi nodes in betweenExitBBs only for cases
//	//  that the blocks were entered from exitBBs[0]
//
//	std::unordered_map<BasicBlock*, Value*> blockEnFromExit0;
//	for (auto BB : betweenExitBBs) {
//		// if the value from exitBBs[0] is used in PHI operands, drop it/replace
//		// with PoisonValue if the value is branch condition the block must be
//		// dominated by exitBBs[0] and all phis
//		//    of this block should be replace with PoisonValue
//		auto c = constructBranchConditionToBBDirect(lowerPhiCtx.Builder, *exitBBs[0], *BB);
//	}
//	// 3. use this flags and phis to build rewritten value for all values
//	// defined in allRegionBBs + exitBBs[0]
//	//    which are used in exitBBs[0] and after.
//
//	// :note: when disconnecting exitBBs[0] successor we replace successor phi
//	// operands with PoisonValue
//	//    and we have to build a SelectInst/PHINode tree in exitBBs[1] to update
//	//    this value using branch conditions along the all original paths from
//	//    exitBBs[0] to exitBBs[1]
//
//	// update CFG and DT (CFG changed at Exit0 outgoing edges).
//	SmallVector<cfg::Update<BasicBlock *>, 8> Updates;
//	auto eBB0term = exitBBs[0]->getTerminator();
//	for (auto *succ : exitBB0Successors) {
//		if (betweenExitBBs.contains(succ)) {
//			eBB0term->replaceSuccessorWith(succ, exitBBs[1]);
//			Updates.push_back({cfg::UpdateKind::Delete, exitBBs[0], succ});
//		}
//	}
//	if (!exitBB0Successors.contains(exitBBs[1]))
//		Updates.push_back({DominatorTree::Insert, exitBBs[0], exitBBs[1]});
//	if (!Updates.empty())
//		DTU.applyUpdates(Updates);
//}

} // namespace hwtHls