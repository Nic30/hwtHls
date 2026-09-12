#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallVector.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>


namespace hwtHls {

void findBlocksBetweenExitBlocksOfRegion(
	const llvm::BasicBlock & BB0,
	const llvm::SetVector<llvm::BasicBlock *> &allRegionBBs,
	const llvm::SetVector<llvm::BasicBlock *> &exitBBs,
	llvm::SetVector<llvm::BasicBlock *> &betweenExitBBs);

/*
 * :note: it is assumed that the blocks do not contains cycles, if they do such edges are ignored
 *      this involves reflective edge (bb0->bb0), and the second edge in loop in format bb0->bb1, bb1->bb0,
 *      for such bb0, bb1 the order is resolved from position in code and from check if the block has successor from blocks
 *      other than bb0
 */
void topologicalSortForBlocks(llvm::SetVector<llvm::BasicBlock *> &blocks, llvm::BasicBlock * BB0=nullptr);

//// :param BB0: the top of region which dominates all blocks in cluster but exit
//// blocks and blocks between them
////  	are dominated by first exitBB and post dominated by second exitBB
//bool fewExitCluster_cutOffExitBBInClusterSuccessors(
//	LowerPhisToSelectInRegionContext& lowerPhiCtx,
//	llvm::DomTreeUpdater &DTU,
//	llvm::SmallVector<llvm::DominatorTree::UpdateType>& updates);

}