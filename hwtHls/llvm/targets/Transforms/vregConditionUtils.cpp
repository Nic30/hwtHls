#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <llvm/IR/Constants.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>

using namespace llvm;
namespace hwtHls {

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

std::pair<llvm::MachineIRBuilder, Register> negateRegisterForInstr(
		MachineInstr &MI, Register reg) {
	MachineBasicBlock *MBB = MI.getParent();
	assert(MBB);
	MachineFunction &MF = *MBB->getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	MachineIRBuilder Builder(*MBB, MI);
	Register reg_n = hwtHls::negateRegister(MRI, Builder, reg);
	return {Builder, reg_n};
}

bool machineInstructionIsSuccessorInSameBlock(const MachineInstr &MI0,
		const MachineInstr &MI1) {
	const auto *I = &MI1;
	const auto *bb = MI0.getParent();
	if (bb != MI1.getParent())
		return false;
	while (I != bb->begin() && I != nullptr) {
		if (I == &MI0)
			return true;
		I = I->getPrevNode();
	}
	return I == &MI0;
}

bool registerIsUsedOnlyInPhisOfSuccessorOrInternallyInBlock(
		const llvm::MachineInstr &defInstr, llvm::Register RegNo) {
	const MachineBasicBlock *MBB = defInstr.getParent();
	assert(MBB);
	const MachineFunction &MF = *MBB->getParent();
	const MachineRegisterInfo &MRI = MF.getRegInfo();
	for (auto &U : MRI.use_instructions(RegNo)) {
		if (!machineInstructionIsSuccessorInSameBlock(defInstr, U)) {
			if (U.getOpcode() == TargetOpcode::G_PHI
					|| U.getOpcode() == TargetOpcode::PHI) {
				auto useMBB = U.getParent();
				bool isSuccessor = false;
				for (const auto &subBB : MBB->successors()) {
					if (subBB == useMBB) {
						isSuccessor = true;
						break;
					}
				}
				if (!isSuccessor) {
					return false;
				}
			} else {
				return false;
			}
		}
	}
	return true;
}

bool registerDefinedInEveryBlock(const MachineRegisterInfo &MRI,
		llvm::iterator_range<llvm::MachineBasicBlock::const_pred_iterator> blocks,
		llvm::Register reg) {
	llvm::SmallDenseSet<const llvm::MachineBasicBlock*> seenBlocks;
	for (const auto &def : MRI.def_instructions(reg)) {
		seenBlocks.insert(def.getParent());
	}
	for (const auto &MBB : blocks) {
		if (seenBlocks.count(MBB) != 1)
			return false;
	}
	return true;
}

}
