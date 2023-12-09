#pragma once

#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {

/*
 * Analyze SwitchInst and if it is used only to select value trough PHIs rewrite it to bunch of SelectInst
 * or as a load from GlobalValue ROM if all PHI operands are constants.
 * */
bool trySwitchToSelectOrRomLoad(llvm::SwitchInst *SI, llvm::IRBuilder<> &Builder,
		llvm::DomTreeUpdater &DTU, size_t MaxRomAddrWidth = 16);
}
