#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/SmallSet.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/machineInstrUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/bitMath.h>

namespace llvm {

bool HwtFpgaCombinerHelper::matchNestedMERGE_VALUES(MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MERGE_VALUES);

	auto DstRegNo = MI.getOperand(0).getReg();
	MachineOperand *otherUse = getNextUseOfRegAfterInstructionExceptMI(DstRegNo,
			MI);
	if (!otherUse) {
		return false;
	}

	MachineInstr *otherMI = otherUse->getParent();
	if (otherMI->getOpcode() != HwtFpga::HWTFPGA_MERGE_VALUES) {
		return false;
	}

	// check that the operand register are not redefined between this and other
	if (checkAnyOperandRedefined(MI, *otherMI)) {
		return false;
	}
	return true;
}

void HwtFpgaCombinerHelper::rewriteNestedMERGE_VALUES(MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MERGE_VALUES);
	auto DstRegNo = MI.getOperand(0).getReg();
	assert(
			(MRI.hasOneDef(DstRegNo)
					|| MI.findRegisterUseOperandIdx(DstRegNo) < 0)
					&& "Dst must have just this def or previous def must not be operand");
	MachineOperand *parentUse = nullptr;
	if (MRI.hasOneUse(DstRegNo)) {
		parentUse = &*MRI.use_begin(DstRegNo);
		assert(parentUse->getReg() == DstRegNo);
	} else {
		MachineInstr *NextInstr =
				getNextUseOfRegInBlock(MI, DstRegNo)->getParent();
		assert(NextInstr && "Should be already checked in matchNestedMux");
		assert(NextInstr->getOpcode() == HwtFpga::HWTFPGA_MERGE_VALUES);
		auto UseOpIndx = NextInstr->findRegisterUseOperandIdx(DstRegNo, false);
		assert(UseOpIndx > 0);
		parentUse = &NextInstr->getOperand(UseOpIndx);
		assert(parentUse->getReg() == DstRegNo);

	}
	// :note: parentMI is a MUX which is using MI
	//    we are now tying to remove MI by inline of MI into parentMI
	//    MI is removed if dst has no other use or MI.dst is parentMi.dst
	MachineInstr *parentMI = parentUse->getParent();
	assert(parentMI->getOpcode() == HwtFpga::HWTFPGA_MERGE_VALUES);

	Builder.setInstrAndDebugLoc(*parentMI);
	auto MIB0 = Builder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES);
	auto &newParentMI = *MIB0.getInstr();
	Observer.changingInstr(newParentMI);
	MIB0.add(parentMI->getOperand(0));
	for (auto &V : hwtHls::MERGE_VALUES_iter_values(*parentMI)) {
		if (V.isReg() && V.getReg() == DstRegNo && V.isUse()) {
			// copy value ops from nested
			for (auto V1 : hwtHls::MERGE_VALUES_iter_values(MI)) {
				MIB0.add(V1);
			}
		} else {
			MIB0.add(V);
		}
	}
	for (const auto& [V, Width] : hwtHls::MERGE_VALUES_iter_valuesWidthPairs(
			*parentMI)) {
		if (V.isReg() && V.getReg() == DstRegNo && V.isUse()) {
			// copy width ops from nested
			for (auto width1 : hwtHls::MERGE_VALUES_iter_widths(MI)) {
				MIB0.add(width1);
			}
		} else {
			MIB0.add(Width);
		}
	}
	// [todo] handle kills for MI value operands and DstReg
	Observer.changedInstr(newParentMI);

	if (DstRegNo == newParentMI.getOperand(0).getReg() || MRI.use_empty(DstRegNo)
			|| all_of(MRI.use_instructions(DstRegNo),
			// MI is only user of its dst
					[&MI](const MachineInstr &_MI) {
						return &_MI == &MI;
					})
		)
		MI.eraseFromParent();
	parentMI->eraseFromParent();
}

}
