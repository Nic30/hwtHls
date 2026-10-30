#pragma once

#include <llvm/CodeGen/MachineRegisterInfo.h>

namespace hwtHls {
// attempt to rename registers so each register has at most 1 def in a block
// :note: used to simplifies search for defs
bool regenerateSsaInMachineFunctionBlocks(llvm::GISelChangeObserver *Observer,
										  llvm::MachineFunction &MF);
bool regenerateSsaInBasicBlock(llvm::MachineRegisterInfo &MRI,
							   const llvm::TargetRegisterInfo *TRI,
							   llvm::GISelChangeObserver *Observer,
							   llvm::MachineBasicBlock &MBB);
}
