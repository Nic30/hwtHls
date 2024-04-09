#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>


namespace hwtHls {

/*
 * The goal of this transformation is similar to llvm::MergedLoadStoreMotion, but it covers a different case.
 * Merge stores to same destination from all predecessors (with unconditional branch to BB) to a new block,
 * potentially updating PHIs and predecessors of BB
 *
 *
 * Search pattern like:
 * PBB0:
 *   store %0, ptr %dst
 *   br label %BB
 * PBB1:
 *   store %1, ptr %dst
 *   br label %BB
 * PBB2:
 *   br label %BB
 *
 * BB:
 *
 *   ...
 *   br i1 %c, label %BB1, label %BBend
 * BB1:
 *   %p = phi [0, %PBB0], [1, %PBB1], [2, %PBB2]
 *   br label %end
 *
 * And rewrite it to:
 * PBB0:
 *   br label %BB.storeMerge
 * PBB1:
 *   br label %BB.storeMerge
 * PBB2:
 *   br label %BB
 * BB.storeMerge:
 *   %p.storeMergePhi = phi [0, %PBB0], [1, %PBB1]
 *   %dst.storeMergeValue = phi [%0, %PBB0], [%1, %PBB1]
 *   br label %BB
 * BB:
 *   %p = phi [%p.storeMergePhi, %BB.storeMerge], [2, %PBB2]
 *
 * */
bool SimplifyCFG2Pass_mergePredecessorsStore(llvm::DomTreeUpdater & DTU, llvm::BasicBlock &BB);

}

