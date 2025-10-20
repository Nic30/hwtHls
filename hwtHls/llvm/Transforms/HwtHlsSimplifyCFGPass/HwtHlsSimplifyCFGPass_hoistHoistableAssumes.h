#pragma once
#include <llvm/IR/BasicBlock.h>

namespace hwtHls {

// hoist llvm.assumes at the top of the single predecessor block if they are marked as hoistable
bool HwtHlsSimplifyCFGPass_hoistHoistableAssumes(llvm::BasicBlock &BB);

}
