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
	virtual unsigned getStackAlignmentSkew(const MachineFunction &MF) const
			override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}
	virtual bool isStackIdSafeForLocalArea(unsigned StackId) const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}
	virtual bool allocateScavengingFrameIndexesNearIncomingSP(
			const MachineFunction &MF) const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}

	virtual bool assignCalleeSavedSpillSlots(MachineFunction &MF,
			const TargetRegisterInfo *TRI, std::vector<CalleeSavedInfo> &CSI,
			unsigned &MinCSFrameIndex, unsigned &MaxCSFrameIndex) const
					override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}

	virtual bool assignCalleeSavedSpillSlots(MachineFunction &MF,
			const TargetRegisterInfo *TRI,
			std::vector<CalleeSavedInfo> &CSI) const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}

	virtual bool enableCalleeSaveSkip(const MachineFunction &MF) const
			override {
		return true;
	}

	virtual bool hasReservedCallFrame(const MachineFunction &MF) const
			override {
		return true;
	}

	virtual bool needsFrameIndexResolution(const MachineFunction &MF) const
			override {
		return false;
	}

	virtual StackOffset getFrameIndexReference(const MachineFunction &MF,
			int FI, Register &FrameReg) const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}

	virtual void determineCalleeSaves(MachineFunction &MF, BitVector &SavedRegs,
			RegScavenger *RS = nullptr) const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}

	virtual TargetStackID::Value getStackIDForScalableVectors() const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");
	}

	virtual bool isSupportedStackID(TargetStackID::Value ID) const override {
		llvm_unreachable("HwtFpgaTarget does not use stack");

	}
};

}
