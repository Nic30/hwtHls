#pragma once
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>

namespace hwtHls {

llvm::Register negateRegister(llvm::MachineRegisterInfo &MRI,
		llvm::MachineIRBuilder &Builder, llvm::Register reg);

std::pair<llvm::MachineIRBuilder, llvm::Register> negateRegisterForInstr(
		llvm::MachineInstr &MI, llvm::Register reg);

bool machineInstructionIsSuccessorInSameBlock(const llvm::MachineInstr &MI0,
		const llvm::MachineInstr &MI1);

bool registerIsUsedOnlyInPhisOfSuccessorOrInternallyInBlock(
		const llvm::MachineInstr &defInstr, llvm::Register reg);

bool registerDefinedInEveryBlock(const llvm::MachineRegisterInfo &MRI,
		llvm::iterator_range<llvm::MachineBasicBlock::const_pred_iterator> blocks,
		llvm::Register reg);
}
