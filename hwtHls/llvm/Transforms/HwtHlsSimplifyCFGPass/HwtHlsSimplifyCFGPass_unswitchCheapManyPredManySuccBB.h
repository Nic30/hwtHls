#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_unswitchCheapManyPredManySuccBB(
	llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
	llvm::BasicBlock &BB, bool &exprChanged);

}
