#pragma once

#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/MachineFunction.h>

#include "genericFpgaMCTargetDesc.h"

#define GET_REGINFO_HEADER
#include "GenericFpgaGenRegisterInfo.inc"

namespace llvm {

class GenericFpgaRegisterInfo: public llvm::GenericFpgaTargetGenRegisterInfo {
public:
	GenericFpgaRegisterInfo();
	const llvm::MCPhysReg*
	getCalleeSavedRegs(const llvm::MachineFunction *MF) const override;
	llvm::BitVector getReservedRegs(const llvm::MachineFunction &MF) const
			override;
	/// Stack Frame Processing Methods
	void eliminateFrameIndex(llvm::MachineBasicBlock::iterator MI, int SPAdj,
			unsigned FIOperandNum, llvm::RegScavenger *RS = NULL) const
					override;
	llvm::Register getFrameRegister(const llvm::MachineFunction &MF) const
			override;

};

}
