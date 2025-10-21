#pragma once

#include <llvm/IR/Instructions.h>

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_normalizeBrCond(llvm::BranchInst *BI);

}
