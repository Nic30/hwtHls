#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/utils_lowerPhiToSelect.h>


namespace hwtHls {

void findBlocksBetweenExitBlocksOfRegion(
	const llvm::SetVector<llvm::BasicBlock *> &allRegionBBs,
	const llvm::SetVector<llvm::BasicBlock *> &exitBBs,
	llvm::SetVector<llvm::BasicBlock *> &betweenExitBBs);

void topologicalSortForBlocks(llvm::SetVector<llvm::BasicBlock *> &blocks, llvm::BasicBlock * BB0=nullptr);

//// :param BB0: the top of region which dominates all blocks in cluster but exit
//// blocks and blocks between them
////  	are dominated by first exitBB and post dominated by second exitBB
//bool fewExitCluster_cutOffExitBBInClusterSuccessors(
//	LowerPhisToSelectInRegionContext& lowerPhiCtx,
//	llvm::DomTreeUpdater &DTU,
//	llvm::SmallVector<llvm::DominatorTree::UpdateType>& updates);

}