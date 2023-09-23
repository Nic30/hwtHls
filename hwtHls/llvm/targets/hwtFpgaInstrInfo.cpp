#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/IR/Constants.h>
#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

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

bool HwtFpgaInstrInfo::shouldSink(const MachineInstr &MI) const {
	// never sink extract because it is instruction with zero cost
	// which reduces amount of data in registers
	//return MI.getOpcode() != HwtFpga::HWTFPGA_EXTRACT;
	return true; // [debug]
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
				//errs() << "Err: cond not empty\n";
				return true;
			}
			assert(!FBB && "FBB should have been null.");
			FBB = TBB;
			Cond.push_back(I->getOperand(0));
			Cond.push_back(MachineOperand::CreateImm(0));
			TBB = I->getOperand(1).getMBB();
		} else if (I->isReturn()) {
			// Returns can't be analyzed, but we should run cleanup.
			CantAnalyze = !isPredicated(*I);
		} else {
			// We encountered other unrecognized terminator. Bail out immediately.
			//errs() << "Err: Unrecognized terminator\n";
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

// based on amdgpu SIInstrInfo::removeBranch
unsigned HwtFpgaInstrInfo::removeBranch(MachineBasicBlock &MBB,
		int *BytesRemoved) const {
	unsigned Count = 0;
	unsigned RemovedSize = 0;
	for (MachineInstr &MI : llvm::make_early_inc_range(MBB.terminators())) {
		// Skip over artificial terminators when removing instructions.
		if (MI.isBranch() || MI.isReturn()) {
			RemovedSize += getInstSizeInBytes(MI);
			MI.eraseFromParent();
			++Count;
		}
	}

	if (BytesRemoved)
		*BytesRemoved = RemovedSize;

	return Count;
}

// :note: the reversed condition must be set explicitly to operand and its register
//    because the parent instruction itself will be likely removed
bool HwtFpgaInstrInfo::reverseBranchCondition(
		SmallVectorImpl<MachineOperand> &Cond) const {
	assert(Cond.size() == 2);
	assert(Cond[0].isReg());
	assert(Cond[0].isUse());
	assert(Cond[1].isImm());
	Cond[1].setImm(!Cond[1].getImm());
	return false;
}

bool HwtFpgaInstrInfo::ClobbersPredicate(MachineInstr &MI,
		std::vector<MachineOperand> &Pred, bool SkipDead) const {
	bool Found = false;
	auto opc = MI.getOpcode();
	switch (opc) {
	case HwtFpga::HWTFPGA_CLOAD: // dst, baseaddr, index, cond
	case HwtFpga::HWTFPGA_CSTORE: { // val, baseaddr, index, cond
		const auto &MO = MI.getOperand(3);
		if (!MO.isReg() || (MO.isDead() && SkipDead))
			break;
		Pred.push_back(MO);
		Pred.push_back(MachineOperand::CreateImm(0));
		Found = true;
		break;
	}

	case HwtFpga::HWTFPGA_MUX: {
		// x = MUX v0 c0
		if (MI.getNumOperands() == 1 + 2) {
			const auto &MO = MI.getOperand(2);
			if (!MO.isReg() || (MO.isDead() && SkipDead))
				break;
			Pred.push_back(MO);
			Pred.push_back(MachineOperand::CreateImm(0));
			Found = true;
		}
	}
	}

	return Found;
}

unsigned HwtFpgaInstrInfo::getPredicationCost(const MachineInstr &MI) const {
	//llvm_unreachable("not implemented");
	return 0;
}

bool HwtFpgaInstrInfo::SubsumesPredicate(ArrayRef<MachineOperand> Pred0,
		ArrayRef<MachineOperand> Pred1) const {
	assert(Pred0.size() == 2 && "Invalid first predicate");
	assert(Pred1.size() == 2 && "Invalid second predicate");

	if (Pred0[0].getReg() == Pred1[0].getReg()
			&& Pred0[1].getImm() == Pred1[1].getImm())
		return true;

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
			(Cond.size() == 2 || Cond.size() == 0)
					&& "branch conditions have 1 component (condReg, isNegatedFlag)!");

	if (Cond.empty()) {
		BuildMI(&MBB, DL, get(TargetOpcode::G_BR)).addMBB(TBB);
		return 1;
	}
	Register Br_n;
	bool isNegated = Cond[1].getImm();
	if (isNegated) {
		MachineFunction &MF = *MBB.getParent();
		MachineRegisterInfo &MRI = MF.getRegInfo();
		// place register negation before first terminator
		MachineIRBuilder Builder(MBB, MBB.end());
		for (auto &t : MBB.terminators()) {
			Builder.setInsertPt(MBB, t);
			break;
		}
		Br_n = hwtHls::negateRegister(MRI, Builder, Cond[0].getReg());
	}
	MachineInstrBuilder MIB = BuildMI(&MBB, DL, get(TargetOpcode::G_BRCOND));
	if (isNegated) {
		MIB.addUse(Br_n);
	} else {
		MIB.add(Cond[0]);
	}
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
	return false;
}

bool HwtFpgaInstrInfo::isProfitableToUnpredicate(MachineBasicBlock &TMBB,
		MachineBasicBlock &FMBB) const {
	return false;
}

bool HwtFpgaInstrInfo::isProfitableToIfCvt(MachineBasicBlock &MBB,
		unsigned NumCycles, unsigned ExtraPredCycles,
		BranchProbability Probability) const {
	//errs() << "HwtFpgaInstrInfo::isProfitableToIfCvt0 Trying " << MBB;
	return true;
}

bool HwtFpgaInstrInfo::isProfitableToIfCvt(MachineBasicBlock &TMBB,
		unsigned NumTCycles, unsigned ExtraTCycles, MachineBasicBlock &FMBB,
		unsigned NumFCycles, unsigned ExtraFCycles,
		BranchProbability Probability) const {
	//errs() << "HwtFpgaInstrInfo::isProfitableToIfCvt1 Trying " << TMBB;
	return true;
}

void HwtFpgaInstrInfo::insertSelect(MachineBasicBlock &MBB,
		MachineBasicBlock::iterator I, const DebugLoc &DL, Register DstReg,
		ArrayRef<MachineOperand> Cond, Register TrueReg,
		Register FalseReg) const {
	// based on AArch64InstrInfo::insertSelect
	if (Cond.size() != 2) {
		llvm_unreachable("NotImplemented");
	}
	MachineRegisterInfo &MRI = MBB.getParent()->getRegInfo();
	const TargetRegisterClass *RC = &HwtFpga::anyregclsRegClass;

	// Pull all virtual register into the appropriate class.
	MRI.constrainRegClass(TrueReg, RC);
	MRI.constrainRegClass(FalseReg, RC);

	bool isNegated = Cond[1].getImm();
	Register Cond_n;
	if (isNegated) {
		MachineFunction &MF = *MBB.getParent();
		MachineRegisterInfo &MRI = MF.getRegInfo();
		MachineIRBuilder Builder(MBB, I);
		Cond_n = hwtHls::negateRegister(MRI, Builder, Cond[0].getReg());
	}

	// Insert the csel.
	auto MIB = BuildMI(MBB, I, DL, get(HwtFpga::HWTFPGA_MUX), DstReg)	//
	.addReg(TrueReg); //
	if (isNegated) {
		MIB.addUse(Cond_n);
	} else {
		MIB.add(Cond[0]);
	}
	MIB.addReg(FalseReg);
}

bool HwtFpgaInstrInfo::canInsertSelect(const MachineBasicBlock &MBB,
		ArrayRef<MachineOperand> Cond, Register DstReg, Register TrueReg,
		Register FalseReg, int &CondCycles, int &TrueCycles,
		int &FalseCycles) const {
	TrueCycles = 0;
	CondCycles = 0;
	FalseCycles = 0;
	return true;
}

bool HwtFpgaInstrInfo::analyzeSelect(const MachineInstr &MI,
		SmallVectorImpl<MachineOperand> &Cond, unsigned &TrueOp,
		unsigned &FalseOp, bool &Optimizable) const {
	switch (MI.getOpcode()) {
	case HwtFpga::HWTFPGA_MUX: {
		if (MI.getNumOperands() == 1 + 1)
			return false; // success, unconditional mux
		if (MI.getNumOperands() != 3 + 1)
			return true;
		TrueOp = 1;
		Cond.push_back(MI.getOperand(2));
		Cond.push_back(MachineOperand::CreateImm(0));
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
		//case HwtFpga::HWTFPGA_CLOAD:
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
	if (Pred.size() != 2)
		llvm_unreachable("NotImplemented");
	switch (opc) {
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE: {
		// dst/val, addr, index, cond
		//assert(MI.getNumOperands() == 4);
		bool hasSomePred = false;
		Register curPred;
		if (MI.getOperand(3).isReg()) {
			hasSomePred = true;
			curPred = MI.getOperand(3).getReg();
		}
		MI.removeOperand(3); // remove current condition
		bool isNegated = Pred[1].getImm();
		Register Cond;
		if (isNegated) {
			auto res = hwtHls::negateRegisterForInstr(MI, Pred[0].getReg());
			Cond = res.second;
		} else {
			Cond = Pred[0].getReg();
		}
		if (hasSomePred) {
			auto *MF = MI.getParent()->getParent();
			MachineRegisterInfo &MRI = MF->getRegInfo();
			MachineIRBuilder Builder(*MI.getParent(), &MI);
			Register CondAndPred = MRI.cloneVirtualRegister(Cond);
			MRI.setType(CondAndPred, LLT::scalar(1));
			Builder.buildInstr(TargetOpcode::G_AND, { CondAndPred }, { Cond,
					curPred });
			Cond = CondAndPred;
		}

		MI.addOperand(MachineOperand::CreateReg(Cond, false));
		break;
	}
	default: {
		/*
		 For example in:
		 bb.0:
		 G_BRCOND %cond, %bb.2
		 bb.1:
		 %v0 = MUX %v1
		 bb.2:
		 ; predecessors: %bb.0, %bb.1
		 G_BRCOND %cond, %bb.4
		 bb.3:
		 ; predecessors: %bb.2
		 use kill %v0
		 bb.4:
		 ; predecessors: %bb.2, %bb.3

		 if v0 is liveout of bb.0 i need to predicate to:

		 bb.0:
		 %v0 = MUX %v1 %cond %v0  ; %v0 and %cond must be added as operands to select proper value for v0
		 bb.2:
		 ; predecessors: %bb.0
		 G_BRCOND %cond, %bb.4
		 bb.3:
		 ; predecessors: %bb.2
		 use kill %v0
		 bb.4:
		 ; predecessors: %bb.2, %bb.3

		 if v0 is not in liveout of bb.0 it should be theoretically possible to:

		 bb.0:
		 %v0 = MUX %v1 ; %v0 is guaranteed to be coming only from original bb.1 and used only if bb.1 was entered
		 bb.2:
		 ; predecessors: %bb.0
		 G_BRCOND %cond, %bb.4
		 bb.3:
		 ; predecessors: %bb.2
		 use kill %v0
		 bb.4:
		 ; predecessors: %bb.2, %bb.3
		 */
		bool isOnlyUsedInPhiOfSuccessorOrInThisBlock = true;
		const MachineBasicBlock *MBB = MI.getParent();
		const MachineFunction &MF = *MBB->getParent();
		const MachineRegisterInfo &MRI = MF.getRegInfo();
		for (const auto &defMO : MI.defs()) {
			if (hwtHls::registerIsUsedOnlyInPhisOfSuccessorOrInternallyInBlock(
					MI, defMO.getReg()))
				continue;
			if (MBB->succ_size() == 1
					&& hwtHls::registerDefinedInEveryBlock(MRI,
							(*MBB->succ_begin())->predecessors(),
							defMO.getReg()))
				continue;
			isOnlyUsedInPhiOfSuccessorOrInThisBlock = false;
			break;
		}
		if (isOnlyUsedInPhiOfSuccessorOrInThisBlock)
			return true; // does not need any predication because it is has only local use

		if (opc == HwtFpga::HWTFPGA_MUX) {
			bool isNegated = Pred[1].getImm();

			if (MI.getNumOperands() == 1 + 1) {
				Register Cond;
				if (isNegated) {
					auto res = hwtHls::negateRegisterForInstr(MI,
							Pred[0].getReg());
					Cond = res.second;
				}
				MI.addOperand(MachineOperand::CreateReg(Cond, false));
				return true;
			} else {
				// if Pred is not satisfied the the output must remain the same, else other conditions in mux should be used to select value

				// pop all operands except dst
				// add current value as first value operand (we already know that the )
				//MI.addOperand(MF, Op)
				MI.getParent()->getParent()->dump();
				MI.dump();
				llvm_unreachable("NotImplemented");
				//MI.removeOperand(OpNo)
			}
		} else {
			MI.getParent()->getParent()->dump();
			MI.dump();
			llvm_unreachable("NotImplemented");
			return false;
		}
	}
	}

	return true; // no need to predicate because register is used only locally in predicated block
}

}
