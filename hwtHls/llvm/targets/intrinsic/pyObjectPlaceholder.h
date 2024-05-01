#pragma once
#include <string>
#include <llvm/IR/Instructions.h>

namespace hwtHls {

extern const std::string PyObjectPlaceholderName;
// args are in format i32 objIndex, *args
bool IsPyObjectPlacehoder(const llvm::CallInst *C);
bool IsPyObjectPlacehoder(const llvm::Function *F);

}
