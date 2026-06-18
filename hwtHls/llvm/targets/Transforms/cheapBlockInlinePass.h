#pragma once

#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/Pass.h>
#include <llvm/CodeGen/MachineFunction.h>

namespace hwtHls {
	
bool isFreeMachineInstr(const llvm::MachineInstr &MI);
bool isCheapMachineInstr(const llvm::MachineInstr &MI);
bool MachineBasicBlock_isCheap_exceptTerminator(const llvm::MachineBasicBlock & MBB);

llvm::FunctionPass* createCheapBlockInlinePass();

}

namespace llvm {
void initializeCheapBlockInlinePass(PassRegistry&);
}
