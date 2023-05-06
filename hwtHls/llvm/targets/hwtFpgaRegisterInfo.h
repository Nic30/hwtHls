#pragma once

#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>

#include "hwtFpgaMCTargetDesc.h"

#define GET_REGINFO_HEADER
#include "HwtFpgaGenRegisterInfo.inc"

namespace llvm {

class HwtFpgaRegisterInfo: public llvm::HwtFpgaTargetGenRegisterInfo {
public:
	HwtFpgaRegisterInfo();
	const llvm::MCPhysReg*
	getCalleeSavedRegs(const llvm::MachineFunction *MF) const override;
	virtual llvm::BitVector getReservedRegs(
			const llvm::MachineFunction &MF) const override;
	/// Stack Frame Processing Methods
	virtual bool eliminateFrameIndex(llvm::MachineBasicBlock::iterator MI,
			int SPAdj, unsigned FIOperandNum,
			llvm::RegScavenger *RS = nullptr) const override;

	llvm::Register getFrameRegister(const llvm::MachineFunction &MF) const
			override;

};

}
