#pragma once
#include <llvm/IR/BasicBlock.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/Analysis/DomTreeUpdater.h>

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BB0, bool &exprChanged);

}
