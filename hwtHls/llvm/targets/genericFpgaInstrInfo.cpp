#include "genericFpgaInstrInfo.h"
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>

#define GET_INSTRINFO_CTOR_DTOR
#include "GenericFpgaGenInstrInfo.inc"

namespace llvm {

static bool isUncondBranchOpcode(int Opc) {
	return Opc == TargetOpcode::G_BR;
}
static bool isCondBranchOpcode(int Opc) {
	return Opc == TargetOpcode::G_BRCOND;
}
static bool isJumpOpcode(int Opc) {
	return Opc == TargetOpcode::G_BRJT;
}

GenericFpgaInstrInfo::GenericFpgaInstrInfo() :
		GenericFpgaTargetGenInstrInfo(-1, -1, -1, -1), RI() {
}

// based on `ARCInstrInfo::analyzeBranch`
bool GenericFpgaInstrInfo::analyzeBranch(MachineBasicBlock &MBB,
		MachineBasicBlock *&TBB, MachineBasicBlock *&FBB,
		SmallVectorImpl<MachineOperand> &Cond, bool AllowModify) const {
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
			if (!Cond.empty())
				return true;

			assert(!FBB && "FBB should have been null.");
			FBB = TBB;
			Cond.push_back(I->getOperand(0));
			TBB = I->getOperand(1).getMBB();
		} else if (I->isReturn()) {
			// Returns can't be analyzed, but we should run cleanup.
			CantAnalyze = !isPredicated(*I);
		} else {
			// We encountered other unrecognized terminator. Bail out immediately.
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

		if (CantAnalyze)
			return true;

		if (I == MBB.begin())
			return false;

		--I;
	}

	// We made it past the terminators without bailing out - we must have
	// analyzed this branch successfully.
	return false;
}

// based on ARCInstrInfo::removeBranch
unsigned GenericFpgaInstrInfo::removeBranch(MachineBasicBlock &MBB,
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

// :note: the reversed condition must be set explicitely to operand and its register
//    because the parent instruction itself will be likely removed
bool GenericFpgaInstrInfo::reverseBranchCondition(
		SmallVectorImpl<MachineOperand> &Cond) const {
	assert(Cond.size() == 1);
	assert(Cond[0].isReg());
	assert(Cond[0].isUse());

	auto * BR = Cond[0].getParent();
	auto & C = BR->getOperand(0); // [attention] original Cond[0] object probably moved
	MachineFunction & MF = *BR->getParent()->getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	Register BR_n = MRI.cloneVirtualRegister(C.getReg()); //MRI.createVirtualRegister(&GenericFpga::AnyRegClsRegClass);//(Cond[0].getReg());
	//MRI.setRegClass(BR_n, &GenericFpga::AnyRegClsRegClass);
	MRI.setType(BR_n, LLT::scalar(1));
	MRI.setType(C.getReg(), LLT::scalar(1));

	MachineIRBuilder Builder(*BR);
	auto NegOne = Builder.buildConstant(LLT::scalar(1), 1);
	MRI.setRegClass(NegOne.getInstr()->getOperand(0).getReg(), &GenericFpga::AnyRegClsRegClass);
    //MRI.invalidateLiveness();
	Builder.buildInstr(TargetOpcode::G_XOR, {BR_n}, {C.getReg(), NegOne});
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

// based on ARCInstrInfo::insertBranch
unsigned GenericFpgaInstrInfo::insertBranch(MachineBasicBlock &MBB,
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

}
