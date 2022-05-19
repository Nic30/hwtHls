#pragma once
#include <llvm/CodeGen/TargetInstrInfo.h>

#include "genericFpgaRegisterInfo.h"

#define GET_INSTRINFO_HEADER
#include "GenericFpgaGenInstrInfo.inc"
#undef GET_INSTRINFO_HEADER

namespace llvm {

class GenericFpgaInstrInfo: public llvm::GenericFpgaTargetGenInstrInfo {
public:
	explicit GenericFpgaInstrInfo();
	const GenericFpgaRegisterInfo& getRegisterInfo() const {
		return RI;
	}
	const TargetRegisterClass* getRegClass(const MCInstrDesc &MCID,
			unsigned OpNum, const TargetRegisterInfo *TRI,
			const MachineFunction &MF) const override {
		return &GenericFpga::AnyRegClsRegClass;
	}

	bool analyzeBranch(MachineBasicBlock &MBB, MachineBasicBlock *&TBB,
			MachineBasicBlock *&FBB, SmallVectorImpl<MachineOperand> &Cond,
			bool AllowModify) const override;
	bool analyzeBranchPredicate(MachineBasicBlock &MBB,
			MachineBranchPredicate &MBP, bool AllowModify = false) const
					override {
		llvm_unreachable("not implemented");
		return true;
	}
	unsigned removeBranch(MachineBasicBlock &MBB,
			int *BytesRemoved = nullptr) const override;
	/// Used mostly by ifconversion
	//  if conversion uses MCOI::Predicate of instructions operands to discover which operand is predicate
	//  the instruction itself has to have MCID::Predicable flag in order to be predictable
	bool reverseBranchCondition(SmallVectorImpl<MachineOperand> &Cond) const
			override;
	bool ClobbersPredicate(MachineInstr &MI, std::vector<MachineOperand> &Pred,
			bool SkipDead) const override {
		llvm_unreachable("not implemented");

		return false;
	}
	unsigned getPredicationCost(const MachineInstr &MI) const override {
		//llvm_unreachable("not implemented");
		return 0;
	}
	bool SubsumesPredicate(ArrayRef<MachineOperand> Pred1,
			ArrayRef<MachineOperand> Pred2) const override {
		llvm_unreachable("not implemented");
		return false;
	}
	unsigned insertBranch(MachineBasicBlock &MBB, MachineBasicBlock *TBB,
			MachineBasicBlock *FBB, ArrayRef<MachineOperand> Cond,
			const DebugLoc &DL, int *BytesAdded = nullptr) const override;
	bool isProfitableToDupForIfCvt(MachineBasicBlock &MBB, unsigned NumCycles,
			BranchProbability Probability) const override {
		llvm_unreachable("not implemented");
		return false;
	}
	bool isProfitableToUnpredicate(MachineBasicBlock &TMBB,
			MachineBasicBlock &FMBB) const override {
		return false;
	}
	bool isProfitableToIfCvt(MachineBasicBlock &MBB, unsigned NumCycles,
			unsigned ExtraPredCycles, BranchProbability Probability) const
					override {
		return true;
	}
	bool isProfitableToIfCvt(MachineBasicBlock &TMBB, unsigned NumTCycles,
			unsigned ExtraTCycles, MachineBasicBlock &FMBB, unsigned NumFCycles,
			unsigned ExtraFCycles, BranchProbability Probability) const
					override {
		return true;
	}
	bool isPredicated(const MachineInstr &MI) const override {
		auto opc = MI.getOpcode();
		unsigned predicateI = -1;
		switch (opc) {
		case GenericFpga::GENFPGA_CLOAD:
			predicateI = 2;
			break;
		case GenericFpga::GENFPGA_CCOPY:
		case GenericFpga::GENFPGA_CSTORE:
			predicateI = 2;
			break;
		default:
			return false;
		}
		//errs() << "MI.getOperand(predicateI).isImm() " << MI << " " << MI.getOperand(predicateI).isImm() << "\n";
		return MI.getNumOperands() > predicateI
				&& !MI.getOperand(predicateI).isImm()
				&& !MI.getOperand(predicateI).isCImm();
	}
	bool PredicateInstruction(MachineInstr &MI,
			ArrayRef<MachineOperand> Pred) const {
		auto opc = MI.getOpcode();
		//unsigned predicateI = -1;
		switch (opc) {
		case GenericFpga::GENFPGA_CLOAD:
		case GenericFpga::GENFPGA_CCOPY:
		case GenericFpga::GENFPGA_CSTORE:
			if (MI.getNumOperands() == 3)
				MI.RemoveOperand(2);
			break;
		default:
			return false;
		}
		assert(Pred.size() == 1);
		MI.addOperand(Pred[0]);
		//llvm_unreachable("not implemented");
		return true;
	}

private:
	const GenericFpgaRegisterInfo RI;
};

}