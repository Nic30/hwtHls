#pragma once
#include <optional>
#include <llvm/IR/Type.h>
#include <llvm/CodeGen/MachineOperand.h>

namespace hwtHls {

llvm::MachineInstr* getLoadOrStoreFromAddrOperand(
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &addrOp);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::tuple<llvm::Type*, size_t, llvm::MachineInstr*> getLoadOrStoreElementType(
		llvm::MachineRegisterInfo &MRI, llvm::MachineInstr &MI);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::optional<std::tuple<llvm::Type*, size_t, llvm::MachineInstr*>> getPointerElementTypeFromAnyLoadOrStore(
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &addrOp);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::pair<llvm::Type*, size_t> getGlobalValueElementTypeAndAddressWidth(
		llvm::MachineInstr &MI);
}
