#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

/*
 * If the block has multiple successors and predecessors, contains only
 * phis+terminator and the branch condition can be statically resolved from the
 * predecessor create jump from predecessor directly to target block instead of
 * BB.
 */
bool HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB(
	llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
	llvm::BasicBlock &BB, bool &exprChanged);

}
