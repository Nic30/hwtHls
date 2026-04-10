#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>


namespace hwtHls {

/*
 * Try to sink store/load at the end of the block to a new block generated for this store,
 * if many predecessors contain the same load/store (except for value)
 * and predecessors ends with the same terminator.
 * :note: A typical case is a block with SwitchInst where many
 *   successor ends with same store. In this case we create a new block to sink
 *   the store into.
 * */
bool HwtHlsSimplifyCFGPass_memSinkToNewBB(llvm::DomTreeUpdater & DTU, llvm::BasicBlock &BB);
}

