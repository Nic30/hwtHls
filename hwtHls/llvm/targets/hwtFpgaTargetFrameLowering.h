#pragma once
#include <llvm/CodeGen/TargetFrameLowering.h>

namespace llvm {

// :note: must be in llvm namespace because of table gen
class HwtFpgaTargetFrameLowering: public llvm::TargetFrameLowering {
public:
	using TargetFrameLowering::TargetFrameLowering;
	/// emitProlog/emitEpilog - These methods insert prolog and epilog code into
	/// the function.
	void emitPrologue(llvm::MachineFunction &MF,
			llvm::MachineBasicBlock &MBB) const override {
	}
	void emitEpilogue(llvm::MachineFunction &MF,
			llvm::MachineBasicBlock &MBB) const override {
	}

	bool hasFP(const llvm::MachineFunction &MF) const override {
		return false;
	}
};

}
