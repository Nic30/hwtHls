#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>


namespace hwtHls {

/*
 * Try to sink
 * Search pattern like:
 *
 * BBStart:
 *   ...
 *   br i1 %c, label %BB1, label %BBend
 * BB1:
 *   ...
 *   store ...
 *   br label %end
 * BBend: ; BBStart dominates BBend
 *   ... ; (no load or store)
 *   br i1 %c, label %BBExit0, label %BBExit1
 *
 * and move branches behind block BBEnd (before BBExit0/BBExit1) or at least tailing stores from each branch
 * */
bool SimplifyCFG2Pass_aggresiveStoreSink(llvm::DomTreeUpdater & DTU, llvm::BasicBlock &BBStart);

}

