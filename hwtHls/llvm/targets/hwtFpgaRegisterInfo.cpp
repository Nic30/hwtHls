#include "hwtFpgaRegisterInfo.h"

#include "hwtFpgaTargetFrameLowering.h"

#define GET_REGINFO_TARGET_DESC
#include "HwtFpgaGenRegisterInfo.inc"

namespace llvm {

HwtFpgaRegisterInfo::HwtFpgaRegisterInfo() :
		llvm::HwtFpgaTargetGenRegisterInfo(0 /* RA */, 0 /* DwarfFlavour */,
				0 /*EHFlavour*/, 0/* PC*/, 0/*HwMode*/) {

}
const llvm::MCPhysReg*
HwtFpgaRegisterInfo::getCalleeSavedRegs(
		const llvm::MachineFunction *MF) const {
	// same as Shang project
	static const llvm::MCPhysReg CSR_Normal_SaveList[] = { 0 };
	return CSR_Normal_SaveList;
}

llvm::BitVector HwtFpgaRegisterInfo::getReservedRegs(
		const llvm::MachineFunction &MF) const {
	return llvm::BitVector(getNumRegs());
}
bool HwtFpgaRegisterInfo::eliminateFrameIndex(
		llvm::MachineBasicBlock::iterator MI, int SPAdj, unsigned FIOperandNum,
		llvm::RegScavenger *RS) const {
	return false; // current instruction was not removed
}
llvm::Register HwtFpgaRegisterInfo::getFrameRegister(
		const llvm::MachineFunction &MF) const {
	llvm_unreachable("No return address register in HwtFpgaRegisterInfo");
	return llvm::HwtFpga::DUMMY_REG_0;
}

}
