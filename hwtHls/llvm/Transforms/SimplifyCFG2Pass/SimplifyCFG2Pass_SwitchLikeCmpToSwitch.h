#pragma once

#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

/*
 * If branch in this block is conditional and is driven by some ICmp x, const check if child block has br driven also by some ICmp x, const
 * and check if successor block contains any and only cheap instructions.
 * Continue stacking blocks from successors while this condition is met. Once block group is found
 * hoist all (cheap) instructions to a block where search has started
 * :note: this is beneficial because it potentially allows for branches to be reduced to SwitchInst
 * :noteL SimplifyCFGOpt::simplifyCondBranch expect block to contain only branch to fold this to SwitchInst
 * */
bool tryHoistFromCheapBlocksWithcSwitchLikeCmpBr(llvm::BranchInst *BI,
		llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater *DTU);

}
