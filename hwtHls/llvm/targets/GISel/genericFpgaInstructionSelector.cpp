#include "genericFpgaInstructionSelector.h"
#include <llvm/CodeGen/GlobalISel/InstructionSelectorImpl.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/Support/Debug.h>

#include "../genericFpgaInstrInfo.h"

#define DEBUG_TYPE "genericfpga-isel"

using namespace llvm;

#define GET_GLOBALISEL_PREDICATE_BITSET
#include "GenericFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_PREDICATE_BITSET

class GenericFpgaTargetInstructionSelector: public InstructionSelector {
public:
	GenericFpgaTargetInstructionSelector(const GenericFpgaTargetMachine &TM,
			const GenericFpgaTargetSubtarget &STI,
			const GenericFpgaRegisterBankInfo &RBI);

	bool select(MachineInstr &I) override;
	static const char* getName() {
		return DEBUG_TYPE;
	}

private:
	bool selectImpl(MachineInstr &I, CodeGenCoverage &CoverageInfo) const;

	const GenericFpgaTargetSubtarget &STI;
	const llvm::GenericFpgaInstrInfo &TII;
	const GenericFpgaRegisterInfo &TRI;
	const GenericFpgaRegisterBankInfo &RBI;

	// FIXME: This is necessary because DAGISel uses "Subtarget->" and GlobalISel
	// uses "STI." in the code generated by TableGen. We need to unify the name of
	// Subtarget variable.
	const GenericFpgaTargetSubtarget *Subtarget = &STI;

#define GET_GLOBALISEL_PREDICATES_DECL
#include "GenericFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_PREDICATES_DECL

#define GET_GLOBALISEL_TEMPORARIES_DECL
#include "GenericFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_TEMPORARIES_DECL
};

#define GET_GLOBALISEL_IMPL
#include "GenericFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_IMPL

GenericFpgaTargetInstructionSelector::GenericFpgaTargetInstructionSelector(
		const GenericFpgaTargetMachine &TM, const GenericFpgaTargetSubtarget &STI,
		const GenericFpgaRegisterBankInfo &RBI)
: InstructionSelector(), STI(STI), TII(*dynamic_cast<const GenericFpgaInstrInfo*>(STI.getInstrInfo())),
TRI(*dynamic_cast<const GenericFpgaRegisterInfo*>(STI.getRegisterInfo())), RBI(RBI),

#define GET_GLOBALISEL_PREDICATES_INIT
#include "GenericFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_PREDICATES_INIT
#define GET_GLOBALISEL_TEMPORARIES_INIT
#include "GenericFpgaGenGlobalISel.inc"
#undef GET_GLOBALISEL_TEMPORARIES_INIT
{
}

bool constrainInstRegOperands(MachineInstr &I, const TargetInstrInfo &TII,
		const TargetRegisterInfo &TRI, const RegisterBankInfo &RBI) {
	MachineBasicBlock &MBB = *I.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();

	for (unsigned OpI = 0, OpE = I.getNumExplicitOperands(); OpI != OpE;
			++OpI) {
		MachineOperand &MO = I.getOperand(OpI);

		// There's nothing to be done on non-register operands.
		if (!MO.isReg())
			continue;

		LLVM_DEBUG(dbgs() << "Converting operand: " << MO << '\n');
		assert(MO.isReg() && "Unsupported non-reg operand");

		Register Reg = MO.getReg();
		// Physical registers don't need to be constrained.
		if (Register::isPhysicalRegister(Reg))
			continue;

		// Register operands with a value of 0 (e.g. predicate operands) don't need
		// to be constrained.
		if (Reg == 0)
			continue;

		// If the operand is a vreg, we should constrain its regclass, and only
		// insert COPYs if that's impossible.
		// constrainOperandRegClass does that for us.
		constrainOperandRegClass(MF, TRI, MRI, TII, RBI, I, I.getDesc(), MO,
				OpI);

		// Tie uses to defs as indicated in MCInstrDesc if this hasn't already been
		// done.
		if (MO.isUse()) {
			int DefIdx = I.getDesc().getOperandConstraint(OpI, MCOI::TIED_TO);
			if (DefIdx != -1 && !I.isRegTiedToUseOperand(DefIdx))
				I.tieOperands(DefIdx, OpI);
		}
	}
	return true;
}
void selectInstrArgs(MachineInstr &I, MachineInstrBuilder &MIB,
		bool firstIsDef) {
	MachineBasicBlock &MBB = *I.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();

	for (unsigned OpI = 0, OpE = I.getNumExplicitOperands(); OpI != OpE;
			++OpI) {
		MachineOperand &MO = I.getOperand(OpI);
		// if operand is a constant value use constant value directly
		if (OpI == 0 && firstIsDef) {
			assert(MO.isReg());
			MIB.addDef(MO.getReg());
			continue;
		}
		if (MO.isReg() && MO.getReg()) {
			if (auto VRegVal = getAnyConstantVRegValWithLookThrough(MO.getReg(),
					MRI)) {
				assert(!(OpI == 0 && firstIsDef));
				auto &C = MF.getFunction().getContext();
				auto *CI = ConstantInt::get(C, VRegVal->Value);
				MIB.addCImm(CI);
				continue;
			}
			if (OpI != 0 || !firstIsDef) {
				MIB.addUse(MO.getReg());
				continue;
			}
		}
		MIB.add(MO);
	}
	MIB.cloneMemRefs(I); // copy part behind :: in "G_LOAD %0:anyregcls :: (volatile load (s4) from %ir.dataIn)"
}

bool GenericFpgaTargetInstructionSelector::select(MachineInstr &I) {
	/*
	 * After selection process finish each VReg has to have some TargetRegisterClass assigned.
	 * */
	assert(I.getParent() && "Instruction should be in a basic block!");
	assert(
			I.getParent()->getParent()
					&& "Instruction should be in a function!");

	auto &MBB = *I.getParent();
	auto &MF = *MBB.getParent();
	auto &MRI = MF.getRegInfo();

	if (!isPreISelGenericOpcode(I.getOpcode())) {
		// Certain non-generic instructions also need some special handling.
		return true;
	}

	if (selectImpl(I, *CoverageInfo))
		return true;

	const TargetRegisterClass &RC = GenericFpga::AnyRegClsRegClass;
	auto Opc = I.getOpcode();
	//llvm::errs() << "GenericFpgaTargetInstructionSelector::select: "
	//		<< TII.getName(Opc) << "\n";
	using namespace TargetOpcode;
	switch (Opc) {
	case G_PHI: {
		I.setDesc(TII.get(PHI));

		Register DstReg = I.getOperand(0).getReg();
		if (!RBI.constrainGenericRegister(DstReg, RC, MRI)) {
			break;
		}
		if (!constrainInstRegOperands(I, TII, TRI, RBI))
			return false;
		return true;
	}
	case G_CONSTANT:
	case G_LOAD:
	case G_STORE: {
		MachineIRBuilder Builder(I);
		unsigned NewOpc;
		switch (Opc) {
		case G_CONSTANT:
			NewOpc = G_CONSTANT;
			break;
		case G_LOAD:
			NewOpc = GenericFpga::GENFPGA_CLOAD;
			break;
		case G_STORE:
			NewOpc = GenericFpga::GENFPGA_CSTORE;
			break;
		default:
			llvm_unreachable(nullptr);
		}
		auto MIB = Builder.buildInstr(NewOpc);
		selectInstrArgs(I, MIB, Opc != G_STORE);
		if (Opc == G_CONSTANT) {
			auto o0 = MIB.getInstr()->getOperand(0).getReg();
			MRI.setType(o0, LLT::scalar(I.getOperand(1).getCImm()->getBitWidth()));
		} else {
			MIB.addImm(1);
		}
		auto newI = Builder.getInsertPt();
		if (!constrainInstRegOperands(*newI, TII, TRI, RBI))
			return false;
		I.eraseFromParent();
		return true;
	}
	case G_IMPLICIT_DEF: // used for function arguments
	case G_ICMP:
	case G_ADD:
	case G_SUB:
	case G_AND:
	case G_MUL:
	case G_OR:
	case G_XOR:
	case G_SELECT:
	case G_INDEXED_STORE:
	case G_INDEXED_LOAD:
	case G_MERGE_VALUES:
	case G_EXTRACT:
	case G_ZEXT:
	case G_SEXT:
	case G_BRCOND:
	case G_BR: {
		MachineIRBuilder Builder(I);
		auto MIB = Builder.buildInstr(Opc);
		selectInstrArgs(I, MIB, Opc != G_BRCOND && Opc != G_BR);
		auto newI = Builder.getInsertPt();
		if (!constrainInstRegOperands(*newI, TII, TRI, RBI))
			return false;
		I.eraseFromParent();
		return true;
	}
	default:
		return false; // some unknown operands (on error it will be printed immediately by caller)
	}

	return false; // all is selected because this is just a dummy selector
}

namespace llvm {
InstructionSelector*
createGenericFpgaInstructionSelector(const GenericFpgaTargetMachine &TM,
		GenericFpgaTargetSubtarget &Subtarget,
		GenericFpgaRegisterBankInfo &RBI) {
	return new GenericFpgaTargetInstructionSelector(TM, Subtarget, RBI);
}
} // end namespace llvm
