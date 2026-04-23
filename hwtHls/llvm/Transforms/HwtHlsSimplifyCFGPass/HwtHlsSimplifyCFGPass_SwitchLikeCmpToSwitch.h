#pragma once

#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

/*
 * If branch in this block is conditional and is driven by some ICmp x, const0 check if child block has br driven also by some ICmp x, const1
 * and check if successor block contains any and only cheap instructions.
 * Continue stacking blocks from successors while this condition is met. Once block group is found
 * hoist all (cheap) instructions to a block where search has started
 * :note: this is beneficial because it potentially allows for branches to be reduced to SwitchInst
 * :note: SimplifyCFGOpt::simplifyCondBranch expect block to contain only branch to fold this to SwitchInst
 *
 * .. code-block:: llvm  
 *     ; for pattern like
 *     bb0:
 *       br c==0, bbExit, bb1
 *     bb1:
 *       br c==1, bbExit, bb2
 *    ...
 *     bbn:
 *       br c==n, bbExit, bbDefault
 *
 *     ; rewrite this to:
 *     bb0.0:
 *        switch c, default: bbDefault {
 *           0: bb0.1
 *           1: bb1
 *           ...
 *        }
 *     bb0.1:
 *        br bbExit
 *     bb1:
 *        br bbExit
 *     ...
 *
 * */
bool tryHoistFromCheapBlocksWithSwitchLikeCmpBr(llvm::BranchInst *BI,
		llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater *DTU, bool & exprChanged);

}
