#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include "hwtFpgaRegisterBankInfo.h"
#include "../hwtFpgaTargetSubtarget.h"
#include "../hwtFpgaTargetMachine.h"

using namespace llvm;
namespace hwtHls::HwtFpgaInstructionSelector {

ConstantInt* machineOperandTryGetConst(LLVMContext &Context,
		MachineRegisterInfo &MRI, MachineOperand &MO) {
	if (MO.isReg() && MO.getReg() && MRI.hasOneDef(MO.getReg())) {
		if (auto VRegVal = getAnyConstantVRegValWithLookThrough(MO.getReg(),
				MRI)) {
			assert(VRegVal.has_value());
			auto *CI = ConstantInt::get(Context, VRegVal->Value);
			return CI;
		}
	}
	return nullptr;
}

void selectInstrArg(MachineFunction &MF,
		MachineInstrBuilder &MIB, MachineRegisterInfo &MRI,
		MachineOperand &MO) {
	if (MO.isReg() && MO.getReg()) {
		if (MO.isDef()) {
			MIB.add(MO);
			return;
		}
		if (MRI.hasOneDef(MO.getReg())) {
			if (auto VRegVal = getAnyConstantVRegValWithLookThrough(MO.getReg(),
					MRI)) {
				assert(VRegVal.has_value());
				auto &C = MF.getFunction().getContext();
				auto *CI = ConstantInt::get(C, VRegVal->Value);
				MIB.addCImm(CI);
				return;
			}
		}
		assert(MO.isUse());
		MIB.add(MO);
	} else {
		MIB.add(MO);
	}
}

void selectInstrArgs(MachineInstr &I, MachineInstrBuilder &MIB,
		bool firstIsDef) {
	MachineBasicBlock &MBB = *I.getParent();
	MachineFunction &MF = *MBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	unsigned OpE = I.getNumExplicitOperands();
	for (unsigned OpI = 0; OpI != OpE; ++OpI) {
		MachineOperand &MO = I.getOperand(OpI);
		// if operand is a constant value use constant value directly
		if (OpI == 0 && firstIsDef) {
			assert(MO.isReg());
			assert(MO.isDef());
			MIB.add(MO);
			continue;
		}
		selectInstrArg(MF, MIB, MRI, MO);
	}
	MIB.cloneMemRefs(I); // copy part behind :: in "G_LOAD %0:anyregcls :: (volatile load (s4) from %ir.dataIn)"
}

}
