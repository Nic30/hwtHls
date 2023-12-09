#pragma once

#include <llvm/Pass.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {
llvm::FunctionPass*
createVRegIfConverter(std::function<bool(const llvm::MachineFunction&)> Ftor);

}

namespace llvm {
void initializeVRegIfConverterPass(PassRegistry&);
}
