#pragma once
#include <optional>
#include <llvm/IR/Type.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <hwtHls/llvm/Transforms/utils/metadataHwtHlsIO.h>

namespace hwtHls {

llvm::MachineInstr* getMirLoadOrStoreFromAddrOperand(
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &addrOp);
/*
 * :returns: element type, 
 * */
struct IoElementMeta {
	llvm::Type* elmTy;
	size_t addressWidth; // number of bits for address signal (0 means no address is required because it is scalar)
	llvm::MachineInstr* ioArgDefiningInstr;
	std::optional<HwtHlsIoMetadata> ioMd;
};
IoElementMeta getMirLoadOrStoreElementType(
		llvm::MachineRegisterInfo &MRI, llvm::MachineInstr &MI);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::optional<IoElementMeta> getMirPointerElementTypeFromAnyLoadOrStore(
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &addrOp);
/*
 * :returns: element type, number of bits for address signal (0 means no address is required because it is scalar)
 * */
std::pair<llvm::Type*, size_t> getMirGlobalValueElementTypeAndAddressWidth(
		llvm::MachineInstr &MI);
}
