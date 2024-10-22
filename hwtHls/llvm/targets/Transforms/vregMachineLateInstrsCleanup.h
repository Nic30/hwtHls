#pragma once

#include <llvm/Pass.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {
llvm::FunctionPass*
createVRegMachineLateInstrsCleanup();

}

namespace llvm {
void initializeVRegMachineLateInstrsCleanupPass(PassRegistry&);
}
