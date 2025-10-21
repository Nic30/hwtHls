#pragma once
#include <llvm/IR/Instructions.h>

namespace hwtHls {
bool HwtHlsSimplifyCFGPass_SwitchReduceRangeUndo(llvm::SwitchInst &I);
}
