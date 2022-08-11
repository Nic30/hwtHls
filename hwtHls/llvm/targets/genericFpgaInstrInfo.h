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
	const GenericFpgaRegisterInfo& getRegisterInfo() const;
	const TargetRegisterClass* getRegClass(const MCInstrDesc &MCID,
			unsigned OpNum, const TargetRegisterInfo *TRI,
			const MachineFunction &MF) const override;
	bool analyzeBranch(MachineBasicBlock &MBB, MachineBasicBlock *&TBB,
			MachineBasicBlock *&FBB, SmallVectorImpl<MachineOperand> &Cond,
			bool AllowModify) const override;
	bool analyzeBranchPredicate(MachineBasicBlock &MBB,
			MachineBranchPredicate &MBP, bool AllowModify = false) const
					override;
	unsigned removeBranch(MachineBasicBlock &MBB,
			int *BytesRemoved = nullptr) const override;
	/// Used mostly by ifconversion
	//  if conversion uses MCOI::Predicate of instructions operands to discover which operand is predicate
	//  the instruction itself has to have MCID::Predicable flag in order to be predictable
	bool reverseBranchCondition(SmallVectorImpl<MachineOperand> &Cond) const
			override;
	bool ClobbersPredicate(MachineInstr &MI, std::vector<MachineOperand> &Pred,
			bool SkipDead) const override;
	unsigned getPredicationCost(const MachineInstr &MI) const override;
	bool SubsumesPredicate(ArrayRef<MachineOperand> Pred1,
			ArrayRef<MachineOperand> Pred2) const override;
	unsigned insertBranch(MachineBasicBlock &MBB, MachineBasicBlock *TBB,
			MachineBasicBlock *FBB, ArrayRef<MachineOperand> Cond,
			const DebugLoc &DL, int *BytesAdded = nullptr) const override;
	bool isProfitableToDupForIfCvt(MachineBasicBlock &MBB, unsigned NumCycles,
			BranchProbability Probability) const override;
	bool isProfitableToUnpredicate(MachineBasicBlock &TMBB,
			MachineBasicBlock &FMBB) const override;
	bool isProfitableToIfCvt(MachineBasicBlock &MBB, unsigned NumCycles,
			unsigned ExtraPredCycles, BranchProbability Probability) const
					override;
	bool isProfitableToIfCvt(MachineBasicBlock &TMBB, unsigned NumTCycles,
			unsigned ExtraTCycles, MachineBasicBlock &FMBB, unsigned NumFCycles,
			unsigned ExtraFCycles, BranchProbability Probability) const
					override;
	void insertSelect(MachineBasicBlock &MBB,
	                  MachineBasicBlock::iterator I, const DebugLoc &DL,
	                  Register DstReg, ArrayRef<MachineOperand> Cond,
	                  Register TrueReg, Register FalseReg) const override;
	bool canInsertSelect(const MachineBasicBlock &MBB,
	                               ArrayRef<MachineOperand> Cond, Register DstReg,
	                               Register TrueReg, Register FalseReg,
	                               int &CondCycles, int &TrueCycles,
	                               int &FalseCycles) const override;
	 bool analyzeSelect(const MachineInstr &MI,
	                             SmallVectorImpl<MachineOperand> &Cond,
	                             unsigned &TrueOp, unsigned &FalseOp,
	                             bool &Optimizable) const override;
	bool isPredicated(const MachineInstr &MI) const override;
	bool PredicateInstruction(MachineInstr &MI,
			ArrayRef<MachineOperand> Pred) const;

private:
	const GenericFpgaRegisterInfo RI;
};

}
