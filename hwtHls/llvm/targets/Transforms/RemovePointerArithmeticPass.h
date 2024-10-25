#pragma once

#include <llvm/Pass.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {
llvm::FunctionPass* createRemovePointerArithmeticPass();
}

namespace llvm {
void initializeRemovePointerArithmeticPassPass(PassRegistry&);
}
