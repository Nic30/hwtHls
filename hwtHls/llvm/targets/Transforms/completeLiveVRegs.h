#pragma once

#pragma once
#include <llvm/Pass.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {
llvm::FunctionPass* createCompleteLiveVRegsPass();
}

namespace llvm {
void initializeCompleteLiveVRegsPass(PassRegistry&);
}
