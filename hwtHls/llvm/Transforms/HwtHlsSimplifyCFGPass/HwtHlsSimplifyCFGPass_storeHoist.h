#pragma once

#include <llvm/IR/BasicBlock.h>
#include <llvm/Analysis/DomTreeUpdater.h>


namespace hwtHls {

/*
 * Try to hoist store at the end of the block
 * If every successor is unreachable or contain same store
 * and there is no instruction with side-efect in between preventing hoist
 * and successor have no other predecessor.
 * :note: typical case is a block with SwitchInst where every
 *   successor begins with store or is unreachable.
 * */
bool HwtHlsSimplifyCFGPass_storeHoist(llvm::BasicBlock &BB);
}

