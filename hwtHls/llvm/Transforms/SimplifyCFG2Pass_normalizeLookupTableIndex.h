#pragma once

#include <llvm/IR/BasicBlock.h>

namespace hwtHls {

bool SimplifyCFGPass2_normalizeLookupTableIndex(llvm::BasicBlock &BB);

}

