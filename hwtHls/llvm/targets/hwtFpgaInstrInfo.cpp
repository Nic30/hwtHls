#include "hwtFpgaInstrInfo.h"
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/IR/Constants.h>

#define GET_INSTRINFO_CTOR_DTOR
#include "HwtFpgaGenInstrInfo.inc"

namespace llvm {

static bool isUncondBranchOpcode(int Opc) {
	return Opc == TargetOpcode::G_BR || Opc == HwtFpga::HWTFPGA_BR;
}
static bool isCondBranchOpcode(int Opc) {
	return Opc == TargetOpcode::G_BRCOND || Opc == HwtFpga::HWTFPGA_BRCOND;
}
static bool isJumpOpcode(int Opc) {
	return Opc == TargetOpcode::G_BRJT;
}

HwtFpgaInstrInfo::HwtFpgaInstrInfo() :
		HwtFpgaTargetGenInstrInfo(-1, -1, -1, -1), RI() {
}

const HwtFpgaRegisterInfo& HwtFpgaInstrInfo::getRegisterInfo() const {
	return RI;
}

const TargetRegisterClass* HwtFpgaInstrInfo::getRegClass(
		const MCInstrDesc &MCID, unsigned OpNum, const TargetRegisterInfo *TRI,
		const MachineFunction &MF) const {
	return &HwtFpga::anyregclsRegClass;
}

// based on `ARCInstrInfo::analyzeBranch`
// check instruction in reverse order if all compatible for predication
bool HwtFpgaInstrInfo::analyzeBranch(MachineBasicBlock &MBB,
		MachineBasicBlock *&TBB, MachineBasicBlock *&FBB,
		SmallVectorImpl<MachineOperand> &Cond, bool AllowModify) const {
	// errs() << "HwtFpgaInstrInfo::analyzeBranch: " << MBB.getFullName() << "\n";
	TBB = FBB = nullptr;
	MachineBasicBlock::iterator I = MBB.end();
	if (I == MBB.begin())
		return false;
	--I;

	while (isPredicated(*I) || I->isTerminator() || I->isDebugValue()) {
		// Flag to be raised on unanalyzeable instructions. This is useful in cases
		// where we want to clean up on the end of the basic block before we bail
		// out.
		bool CantAnalyze = false;

		// Skip over DEBUG values and predicated nonterminators.
		while (I->isDebugInstr() || !I->isTerminator()) {
			if (I == MBB.begin())
				return false;
			--I;
		}

		if (isJumpOpcode(I->getOpcode())) {
			// Indirect branches and jump tables can't be analyzed, but we still want
			// to clean up any instructions at the tail of the basic block.
			CantAnalyze = true;
		} else if (isUncondBranchOpcode(I->getOpcode())) {
			TBB = I->getOperand(0).getMBB();
		} else if (isCondBranchOpcode(I->getOpcode())) {
			// Bail out if we encounter multiple conditional branches.
			if (!Cond.empty()) {
				// errs() << "Err: cond not empty\n";
				return true;
			}
			assert(!FBB && "FBB should have been null.");
			FBB = TBB;
			Cond.push_back(I->getOperand(0));
			TBB = I->getOperand(1).getMBB();
		} else if (I->isReturn()) {
			// Returns can't be analyzed, but we should run cleanup.
			CantAnalyze = !isPredicated(*I);
		} else {
			// We encountered other unrecognized terminator. Bail out immediately.
			// errs() << "Err: Unrecognized terminator\n";
			return true;
		}

		// Cleanup code - to be run for unpredicated unconditional branches and
		//                returns.
		if (!isPredicated(*I)
				&& (isUncondBranchOpcode(I->getOpcode())
						|| isJumpOpcode(I->getOpcode()) || I->isReturn())) {
			// Forget any previous condition branch information - it no longer
			// applies.
			Cond.clear();
			FBB = nullptr;

			// If we can modify the function, delete everything below this
			// unconditional branch.
			if (AllowModify) {
				MachineBasicBlock::iterator DI = std::next(I);
				while (DI != MBB.end()) {
					MachineInstr &InstToDelete = *DI;
					++DI;
					InstToDelete.eraseFromParent();
				}
			}
		}

		if (CantAnalyze) {
			//errs() << "Err can not analyze\n";
			return true;
		}

		if (I == MBB.begin())
			return false; // all in this block was analyzed successfully

		--I;
	}

	// We made it past the terminators without bailing out - we must have
	// analyzed this branch successfully.
	return false;
}

bool HwtFpgaInstrInfo::analyzeBranchPredicate(MachineBasicBlock &MBB,
		MachineBranchPredicate &MBP, bool AllowModify) const {
	llvm_unreachable("not implemented");
	return true;
}

// based on ARCInstrInfo::removeBranch
unsigned HwtFpgaInstrInfo::removeBranch(MachineBasicBlock &MBB,
		int *BytesRemoved) const {
	assert(!BytesRemoved && "Code size not handled");
	MachineBasicBlock::iterator I = MBB.getLastNonDebugInstr();
	if (I == MBB.end())
		return 0;

	if (!isUncondBranchOpcode(I->getOpcode())
			&& !isCondBranchOpcode(I->getOpcode()))
		return 0;

	// Remove the branch.
	I->eraseFromParent();

	I = MBB.end();

	if (I == MBB.begin())
		return 1;
	--I;
	if (!isCondBranchOpcode(I->getOpcode()))
		return 1;

	// Remove the branch.
	I->eraseFromParent();
	return 2;
}

Register negateRegister(MachineRegisterInfo &MRI, MachineIRBuilder &Builder,
		Register reg) {
	if (MRI.hasOneDef(reg)) {
		for (auto &I : MRI.def_instructions(reg)) {
			switch (I.getOpcode()) {
			case TargetOpcode::G_XOR: {
				auto &O1 = I.getOperand(2);
				if (O1.isCImm() && O1.getCImm()->getBitWidth() == 1
						&& O1.getCImm()->equalsInt(1)) {
					return I.getOperand(1).getReg();
				}
				if (MRI.hasOneDef(O1.getReg())) {
					if (auto VRegVal = getAnyConstantVRegValWithLookThrough(
							O1.getReg(), MRI)) {
						if (VRegVal.has_value() && VRegVal.value().Value == 1) {
							return I.getOperand(1).getReg();
						}
					}
				}
				break;
			}
			case HwtFpga::HWTFPGA_NOT: {
				return I.getOperand(1).getReg();
			}
			}
		}
	}
	Register BR_n = MRI.cloneVirtualRegister(reg); //MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);//(Cond[0].getReg());
	//MRI.setRegClass(BR_n, &HwtFpga::anyregclsRegClass);
	MRI.setType(BR_n, LLT::scalar(1));
	MRI.setType(reg, LLT::scalar(1));

	auto NegOne = Builder.buildConstant(LLT::scalar(1), 1);
	MRI.setRegClass(NegOne.getInstr()->getOperand(0).getReg(),
			&HwtFpga::anyregclsRegClass);
	//MRI.invalidateLiveness();
	Builder.buildInstr(TargetOpcode::G_XOR, { BR_n }, { reg, NegOne });

	return BR_n;
}

// :note: the reversed condition must be set explicitely to operand and its register
//    because the parent instruction itself will be likely removed
bool HwtFpgaInstrInfo::reverseBranchCondition(
		SmallVectorImpl<MachineOperand> &Cond) const {
	assert(Cond.size() == 1);
	assert(Cond[0].isReg());
	assert(Cond[0].isUse());

	auto *BR = Cond[0].getParent();
	auto &C = BR->getOperand(0); // [attention] original Cond[0] object probably moved, modifying it will break use lists
	MachineFunction &MF = *BR->getParent()->getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();

	MachineIRBuilder Builder(*BR);
	Register BR_n = negateRegister(MRI, Builder, C.getReg());

	//BR->getOperand(0).setReg(BR_n);
	//C.ChangeToRegister(BR_n, false);
	C.setReg(BR_n);
	//C.setIsUse();
	//C.ChangeToRegister(BR_n, false);
	Cond.pop_back();
	Cond.push_back(C);

	MRI.verifyUseLists();

	return false;
}

bool HwtFpgaInstrInfo::ClobbersPredicate(MachineInstr &MI,
		std::vector<MachineOperand> &Pred, bool SkipDead) const {
	llvm_unreachable("not implemented");

	return false;
}

unsigned HwtFpgaInstrInfo::getPredicationCost(
		const MachineInstr &MI) const {
	//llvm_unreachable("not implemented");
	return 0;
}

bool HwtFpgaInstrInfo::SubsumesPredicate(ArrayRef<MachineOperand> Pred1,
		ArrayRef<MachineOperand> Pred2) const {
	llvm_unreachable("not implemented");
	return false;
}

// based on ARCInstrInfo::insertBranch
unsigned HwtFpgaInstrInfo::insertBranch(MachineBasicBlock &MBB,
		MachineBasicBlock *TBB, MachineBasicBlock *FBB,
		ArrayRef<MachineOperand> Cond, const DebugLoc &DL,
		int *BytesAdded) const {
	assert(!BytesAdded && "Code size not handled.");

	// Shouldn't be a fall through.
	assert(TBB && "insertBranch must not be told to insert a fallthrough");
	assert(
			(Cond.size() == 1 || Cond.size() == 0)
					&& "branch conditions have 1 component!");

	if (Cond.empty()) {
		BuildMI(&MBB, DL, get(TargetOpcode::G_BR)).addMBB(TBB);
		return 1;
	}
	MachineInstrBuilder MIB = BuildMI(&MBB, DL, get(TargetOpcode::G_BRCOND));
	MIB.add(Cond[0]);
	MIB.addMBB(TBB);

	// One-way conditional branch.
	if (!FBB) {
		return 1;
	}

	// Two-way conditional branch.
	BuildMI(&MBB, DL, get(TargetOpcode::G_BR)).addMBB(FBB);
	return 2;
}

bool HwtFpgaInstrInfo::isProfitableToDupForIfCvt(MachineBasicBlock &MBB,
		unsigned NumCycles, BranchProbability Probability) const {
	llvm_unreachable("not implemented");
	return false;
}

bool HwtFpgaInstrInfo::isProfitableToUnpredicate(MachineBasicBlock &TMBB,
		MachineBasicBlock &FMBB) const {
	return false;
}

bool HwtFpgaInstrInfo::isProfitableToIfCvt(MachineBasicBlock &MBB,
		unsigned NumCycles, unsigned ExtraPredCycles,
		BranchProbability Probability) const {
	return true;
}

bool HwtFpgaInstrInfo::isProfitableToIfCvt(MachineBasicBlock &TMBB,
		unsigned NumTCycles, unsigned ExtraTCycles, MachineBasicBlock &FMBB,
		unsigned NumFCycles, unsigned ExtraFCycles,
		BranchProbability Probability) const {
	return true;
}

void HwtFpgaInstrInfo::insertSelect(MachineBasicBlock &MBB,
		MachineBasicBlock::iterator I, const DebugLoc &DL, Register DstReg,
		ArrayRef<MachineOperand> Cond, Register TrueReg,
		Register FalseReg) const {
	// based on AArch64InstrInfo::insertSelect
	if (Cond.size() != 1) {
		llvm_unreachable("NotImplemented");
	}
	MachineRegisterInfo &MRI = MBB.getParent()->getRegInfo();
	const TargetRegisterClass *RC = &HwtFpga::anyregclsRegClass;

	// Pull all virtual register into the appropriate class.
	MRI.constrainRegClass(TrueReg, RC);
	MRI.constrainRegClass(FalseReg, RC);

	// Insert the csel.
	BuildMI(MBB, I, DL, get(HwtFpga::HWTFPGA_MUX), DstReg)	//
	.addReg(TrueReg) //
	.add(Cond[0]) //
	.addReg(FalseReg);
}

bool HwtFpgaInstrInfo::canInsertSelect(const MachineBasicBlock &MBB,
		ArrayRef<MachineOperand> Cond, Register DstReg, Register TrueReg,
		Register FalseReg, int &CondCycles, int &TrueCycles,
		int &FalseCycles) const {
	return true;
}

bool HwtFpgaInstrInfo::analyzeSelect(const MachineInstr &MI,
		SmallVectorImpl<MachineOperand> &Cond, unsigned &TrueOp,
		unsigned &FalseOp, bool &Optimizable) const {
	switch (MI.getOpcode()) {
	case HwtFpga::HWTFPGA_MUX: {
		if (MI.getNumOperands() != 3 + 1)
			return true;
		TrueOp = 1;
		Cond.push_back(MI.getOperand(2));
		FalseOp = 3;
		return false; // success
	}
	case TargetOpcode::PHI:
	case TargetOpcode::G_PHI:
	case TargetOpcode::G_SELECT:
		llvm_unreachable("NotImplemented");
	default:
		return true; // instruction can be analyzed
	}
}

bool HwtFpgaInstrInfo::isPredicated(const MachineInstr &MI) const {
	auto opc = MI.getOpcode();
	switch (opc) {
	case TargetOpcode::PHI:
	case TargetOpcode::G_PHI:
	case TargetOpcode::G_SELECT:
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE:
	case HwtFpga::HWTFPGA_MUX:
		return false; // can be predicate infinity times
	default:
		return false;
	}
	//errs() << "MI.getOperand(predicateI).isImm() " << MI << " " << MI.getOperand(predicateI).isImm() << "\n";
	// return	!MI.getOperand(predicateI).isImm()
	// 		&& !MI.getOperand(predicateI).isCImm();
}

bool HwtFpgaInstrInfo::PredicateInstruction(MachineInstr &MI,
		ArrayRef<MachineOperand> Pred) const {
	auto opc = MI.getOpcode();
	if (Pred.size() != 1)
		llvm_unreachable("NotImplemented");
	//unsigned predicateI = -1;
	switch (opc) {
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE:
		// dst/val, addr, index, predicate
		assert(MI.getNumOperands() == 4);
		if (MI.getOperand(3).isReg()) {
			llvm_unreachable("NotImplemented");
		}
		MI.removeOperand(3);
		break;
	case HwtFpga::HWTFPGA_MUX:
		llvm_unreachable("NotImplemented");
	default:
		MI.dump();
		llvm_unreachable("NotImplemented");
		return false;
	}
	MI.addOperand(Pred[0]);
	return true;
}

}