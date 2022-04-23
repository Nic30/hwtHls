#include "genericFpgaRegisterInfo.h"

#include "genericFpgaTargetFrameLowering.h"

#define GET_REGINFO_TARGET_DESC
#include "GenericFpgaGenRegisterInfo.inc"

namespace llvm {

GenericFpgaRegisterInfo::GenericFpgaRegisterInfo() :
		llvm::GenericFpgaTargetGenRegisterInfo(0) {

}
const llvm::MCPhysReg*
GenericFpgaRegisterInfo::getCalleeSavedRegs(
		const llvm::MachineFunction *MF) const {
	// same as Shang project
	static const llvm::MCPhysReg CSR_Normal_SaveList[] = { 0 };
	return CSR_Normal_SaveList;
}

llvm::BitVector GenericFpgaRegisterInfo::getReservedRegs(
		const llvm::MachineFunction &MF) const {
	return llvm::BitVector(getNumRegs());
}
void GenericFpgaRegisterInfo::eliminateFrameIndex(
		llvm::MachineBasicBlock::iterator MI, int SPAdj, unsigned FIOperandNum,
		llvm::RegScavenger *RS) const {
}
llvm::Register GenericFpgaRegisterInfo::getFrameRegister(
		const llvm::MachineFunction &MF) const {
	llvm_unreachable("No return address register in GenericFpgaRegisterInfo");
	return llvm::GenericFpga::DUMMY_REG_0;
}

}
