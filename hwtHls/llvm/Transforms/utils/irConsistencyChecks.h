#pragma once

#include <llvm/IR/Function.h>

namespace hwtHls {
void verifyUsesList(const llvm::Function &F);
}
