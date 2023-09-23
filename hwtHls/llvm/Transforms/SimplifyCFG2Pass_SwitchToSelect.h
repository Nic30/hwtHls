#pragma once

#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/Analysis/DomTreeUpdater.h>
#include <llvm/IR/IRBuilder.h>

namespace hwtHls {
bool trySwitchToSelect(llvm::SwitchInst *SI, llvm::IRBuilder<> &Builder, llvm::DomTreeUpdater & DTU);
}
