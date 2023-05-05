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
std::pair<llvm::Type*, size_t> getLoadOrStoreElementType(
		llvm::MachineRegisterInfo &MRI, llvm::MachineInstr &MI);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::optional<std::pair<llvm::Type*, size_t>> getPointerElementTypeFromAnyLoadOrStore(
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &addrOp);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::pair<llvm::Type*, size_t> getGlobalValueElementTypeAndAddressWidth(
		llvm::MachineInstr &MI);
}
