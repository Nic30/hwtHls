#include "genericFpgaRegisterInfo.h"

#include "genericFpgaTargetFrameLowering.h"

#define GET_REGINFO_TARGET_DESC
#include "GenericFpgaGenRegisterInfo.inc"

namespace llvm {

GenericFpgaRegisterInfo::GenericFpgaRegisterInfo() :
		llvm::GenericFpgaTargetGenRegisterInfo(0 /* RA */, 0 /* DwarfFlavour */,
				0 /*EHFlavour*/, 0/* PC*/, 0/*HwMode*/) {

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
bool GenericFpgaRegisterInfo::eliminateFrameIndex(
		llvm::MachineBasicBlock::iterator MI, int SPAdj, unsigned FIOperandNum,
		llvm::RegScavenger *RS) const {
	return false; // current instruction was not removed
}
llvm::Register GenericFpgaRegisterInfo::getFrameRegister(
		const llvm::MachineFunction &MF) const {
	llvm_unreachable("No return address register in GenericFpgaRegisterInfo");
	return llvm::GenericFpga::DUMMY_REG_0;
}

}
