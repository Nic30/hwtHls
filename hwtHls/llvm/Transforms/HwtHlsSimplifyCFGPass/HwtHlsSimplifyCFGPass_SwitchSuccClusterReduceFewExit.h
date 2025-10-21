#pragma once

#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

// reduce empty successor blocks after SwitchInst if there are just 2 unique exit blocks, no loop
// (the instruction which can be speculated should already be hoisted by :func:`HoistFromSwitchSuccessors`)
bool HwtHlsSimplifyCFGPass_SwitchSuccClusterReduceFewExit(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		llvm::SwitchInst &SI, bool &exprChanged);
}
