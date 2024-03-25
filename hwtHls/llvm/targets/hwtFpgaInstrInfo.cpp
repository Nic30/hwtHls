#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/IR/Constants.h>
#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/machineInstrUtils.h>

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
	return MI.getOpcode() != HwtFpga::HWTFPGA_EXTRACT;
}

// based on `ARCInstrInfo::analyzeBranch`
// check instruction in reverse order if all compatible for predication
bool HwtFpgaInstrInfo::analyzeBranch(MachineBasicBlock &MBB,
		MachineBasicBlock *&TBB, MachineBasicBlock *&FBB,
		SmallVectorImpl<MachineOperand> &Cond, bool AllowModify) const {
	MachineFunction::iterator Fallthrough = MBB.getIterator();
	++Fallthrough;
	//TBB = &*Fallthrough;
	TBB = nullptr;
	FBB = nullptr;
	MachineBasicBlock::iterator I = MBB.end();
	if (I == MBB.begin())
		return false; // empty blocks -> no terminators
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
				return true; // Err: cond not empty
			}
			assert(!FBB && "FBB should have been null.");
			if (TBB == nullptr)
				TBB = &*Fallthrough;
			else
				FBB = TBB;
			Cond.push_back(I->getOperand(0));
			Cond.push_back(MachineOperand::CreateImm(0));
			TBB = I->getOperand(1).getMBB();
		} else if (I->isReturn()) {
			// Returns can't be analyzed, but we should run cleanup.
			CantAnalyze = !isPredicated(*I);
		} else {
			// We encountered other unrecognized terminator. Bail out immediately.
			return true; // Err: Unrecognized terminator
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
			return true; // Err can not analyze
		}

		if (I == MBB.begin()) {
			return false; // all in this block was analyzed successfully
		}
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
	//assert(Cond[0].isUse());
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
	if (Pred0.size() != Pred1.size()) {
		return false;
	}
	assert((Pred0.size() % 2 == 0) && "Invalid first predicate");
	assert((Pred1.size() % 2 == 0) && "Invalid second predicate");

	auto p0 = Pred0.begin();
	auto p1 = Pred1.begin();
	for (;;) {
		if (p0 == Pred0.end()) {
			if (p1 == Pred1.end())
				break;
			else
				return false;
		}
		if (p1 == Pred1.end()) {
			return false;
		}
		assert(p0->isReg());
		assert(p1->isReg());

		if (p0->getReg() != p1->getReg()) {
			return false;
		}
		++p0;
		++p1;
		assert(p0->isImm());
		assert(p1->isImm());
		if (p0->getImm() != p1->getImm()) {
			return false;
		}
	}

	return true;
}

// based on ARCInstrInfo::insertBranch
unsigned HwtFpgaInstrInfo::insertBranch(MachineBasicBlock &MBB,
		MachineBasicBlock *TBB, MachineBasicBlock *FBB,
		ArrayRef<MachineOperand> Cond, const DebugLoc &DL,
		int *BytesAdded) const {
	// :note: Cond meaning can not be altered, T/F can not be swapped because code in transformations like IfConverter
	// uses condition to build another condition and reversing the condition would break all expressions where this condition is used.
	// :attention: Cond must be updated if different register was used, because current may be subject to DCE and the Cond would
	//  become invalid over the time
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
	assert(Cond[0].isReg());

	MachineOperand Br_cond = Cond[0];
	bool isNegated = Cond[1].getImm();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	auto CondMutable = reinterpret_cast<MutableArrayRef<MachineOperand>&>(Cond);
	bool CondWasKill = Cond[0].isKill();
	if (isNegated) {
		MachineOperand *_Br_n = hwtHls::getRegisterNegationIfExits(MRI, MBB,
				MBB.end(), Br_cond.getReg(), CondWasKill);
		if (_Br_n) {
			// use existing negation of register
			Br_cond = CondMutable[0] = *_Br_n;
			CondMutable[1].setImm(0); // negated twice = not negated

			//} else if (FBB) {
			//	// swap T/F to avoid negation
			//	std::swap(TBB, FBB);
		} else {
			// place register negation before first terminator
			MachineIRBuilder Builder(MBB, MBB.terminators().begin());
			Br_cond = CondMutable[0] = hwtHls::_negateRegister(MRI, Builder,
					Cond[0].getReg(), Cond[0].isKill());
			CondMutable[1].setImm(0); // negated twice = not negated
		}
	}
	MachineInstrBuilder MIB = BuildMI(&MBB, DL, get(TargetOpcode::G_BRCOND));
	MIB.addUse(Br_cond.getReg(),
			MRI.use_empty(Br_cond.getReg()) || CondWasKill ?
					RegState::Kill : 0);
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
	//case TargetOpcode::PHI:
	//case TargetOpcode::G_PHI:
	//case TargetOpcode::G_SELECT:
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE:
		//{
		//	size_t predicateI = 3;
		//	return !MI.getOperand(predicateI).isImm()
		//			&& !MI.getOperand(predicateI).isCImm();
		//}
	case HwtFpga::HWTFPGA_MUX:
		return false; // can be predicate infinity times
	default:
		return false;
	}
}

bool HwtFpgaInstrInfo::PredicateInstruction(MachineInstr &MI,
		ArrayRef<MachineOperand> Pred) const {
	auto opc = MI.getOpcode();
	if (Pred.size() != 2)
		llvm_unreachable("NotImplemented - predicate with multiple terms");

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
			Register CondAndPred;
			if (Cond == curPred) {
				CondAndPred = Cond;
			} else {
				CondAndPred = MRI.cloneVirtualRegister(Cond);
				MRI.setType(CondAndPred, LLT::scalar(1));
				Builder.buildInstr(TargetOpcode::G_AND, { CondAndPred }, { Cond,
						curPred });
				Cond = CondAndPred;
			}
		}

		MI.addOperand(MachineOperand::CreateReg(Cond, false));
		// :note: implicit operand should be added by caller of this function (if required)
		//if (opc == HwtFpga::HWTFPGA_CLOAD) {
		//	auto DstReg = MI.getOperand(0).getReg();
		//	if (!MI.hasRegisterImplicitUseOperand(DstReg)) { // add dst as implicit operand for liveness analysis
		//		auto &MBB = *MI.getParent();
		//		MachineFunction &MF = *MBB.getParent();
		//		MachineRegisterInfo &MRI = MF.getRegInfo();
		//		if (!MRI.use_empty(DstReg)) {
		//			MI.addOperand(MachineOperand::CreateReg(DstReg, /*IsDef*/
		//			false, /*IsImp*/true));
		//		}
		//	}
		//}
		return true;
	}
	case HwtFpga::HWTFPGA_BR:
	case HwtFpga::G_BR: {
		bool isNegated = Pred[1].getImm();
		Register Cond;
		if (isNegated) {
			auto res = hwtHls::negateRegisterForInstr(MI, Pred[0].getReg());
			Cond = res.second;
		} else {
			Cond = Pred[0].getReg();
		}
		MI.setDesc(
				get(
						opc == HwtFpga::HWTFPGA_BR ?
								HwtFpga::HWTFPGA_BRCOND : HwtFpga::G_BRCOND));
		auto BB = MI.getOperand(0);
		MI.removeOperand(0);
		MI.addOperand(MachineOperand::CreateReg(Cond, false));
		MI.addOperand(BB);
		return true;
	}

	default:
		return false;
	}
}

}
