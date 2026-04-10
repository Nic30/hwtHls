#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>


namespace hwtHls {

/*
 * Try to hoist store/load at the beginning of the block to a new block generated for this load/store,
 * if many successors contain the same load/store (except for value)
 * and successors have just this single predecessor.
 *
 * :note: A typical case is a block with SwitchInst where many
 *   successor begin with the same load. In this case we create a new block to hoist
 *   the load into and partly copy the terminator for this new block.
 * :note: HwtHlsSimplifyCFGPass_storeHoist hoist to a BB,
 *        HwtHlsSimplifyCFGPass_memHoistToNewBB creates a new common predecessor block if required
 **/
bool HwtHlsSimplifyCFGPass_memHoistToNewBB(llvm::DomTreeUpdater & DTU, llvm::BasicBlock &BB);
}

