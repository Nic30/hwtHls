#pragma once

#include <llvm/IR/BasicBlock.h>

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_normalizeLookupTableIndex(llvm::BasicBlock &BB);

}

