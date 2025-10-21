#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>

namespace hwtHls {
// If predecessor block is cheap and has single successor, try merge
// this block at the top of the successor block (in this case BB0 to BB1)
//
//   |/
//  BB0
//   |/
//  BB1
//
// :note: this function starts search on BB0 in the figure
// :note: similar to llvm::MergeBlockIntoPredecessor() but supports multiple pred/succ scenario
// :note: this is useful for merging of outer loops which can be merged without much overhead
bool HwtHlsSimplifyCFGPass_speculatePredecessor(llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BB);
}
