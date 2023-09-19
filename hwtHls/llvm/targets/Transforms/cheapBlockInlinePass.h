#pragma once
#include <llvm/Pass.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {
llvm::FunctionPass* createCheapBlockInlinePass();
}

namespace llvm {
void initializeCheapBlockInlinePass(PassRegistry&);
}
