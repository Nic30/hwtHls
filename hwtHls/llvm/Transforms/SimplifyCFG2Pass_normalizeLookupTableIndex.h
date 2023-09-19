#pragma once

#include <llvm/IR/BasicBlock.h>

namespace hwtHls {

bool SimplifyCFG2Pass_normalizeLookupTableIndex(llvm::BasicBlock &BB);

}

