#pragma once
#include <string>
#include <llvm/IR/Instruction.h>

namespace hwtHls {

// behavior is similar to Attribute::AttrKind::Speculatable
// but applies to any instruction not just function calls
extern const std::string METADATA_NAME_sideEffect_allowHoist;
void setMetadataSideeffectAllowHoist(llvm::Instruction &I);
bool hasMetadataSideeffectAllowHoist(llvm::Instruction &I);
}
