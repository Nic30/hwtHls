#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>

namespace llvm {

bool HwtFpgaCombinerHelper::matchIsExtractOnMergeValues(
		llvm::MachineInstr &MI) {
	auto _src = MI.getOperand(1);
	if (_src.isReg()) {
		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			return src->getParent()->getOpcode()
					== HwtFpga::HWTFPGA_MERGE_VALUES;
		}
	}
	return false;
}

void addSrcOperand(MachineInstrBuilder &MIB,
		HwtFpgaCombinerHelper::ConcatMember &src) {
	if (src.op.isReg() && src.op.isDef())
		MIB.addUse(src.op.getReg()); // convert def to use
	else {
		MIB.add(src.op);
	}
}

void HwtFpgaCombinerHelper::rewriteExtractOnMergeValues(
		llvm::MachineInstr &MI) {
	// MI.operands() == $dst $src $offset $dstWidth
	std::vector<ConcatMember> concatMembers;
	//uint64_t mainOffset = MI.getOperand(2).getImm();
	uint64_t mainWidth = MI.getOperand(3).getImm();
	uint64_t currentOffset = 0;
	bool didReduce = collectConcatMembers(MI.getOperand(0), concatMembers, 0,
			mainWidth, currentOffset, 0, mainWidth);
	if (!didReduce)
		return;
	assert(
			concatMembers.size()
					&& "There must be something which EXTRACT selects");
	if (concatMembers.size() == 1) {
		auto &src = concatMembers.back();
		// we may be able to use item directly of we may build an EXTRACT
		if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
			if (src.op.isReg()) {
				MRI.replaceRegWith(MI.getOperand(0).getReg(), src.op.getReg());
				if (src.op.isUndef()) {
					for (auto &U : MRI.use_operands(src.op.getReg())) {
						U.setIsUndef();
					}
				}

			} else if (src.op.isCImm()) {
				Builder.setInstrAndDebugLoc(MI);
				Register srcReg = MRI.createVirtualRegister(
						&HwtFpga::anyregclsRegClass);
				Builder.buildConstant(srcReg, *src.op.getCImm());
				MRI.replaceRegWith(MI.getOperand(0).getReg(), srcReg);
			} else {
				llvm_unreachable(
						"HwtFpgaCombinerHelper::rewriteExtractOnMergeValues unexpected type of src operand");
			}
		} else {
			Builder.setInstrAndDebugLoc(MI);
			auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
			auto& newMI = *MIB.getInstr();
			Observer.changingInstr(newMI);
			// $dst $src $offset $dstWidth
			MIB.addDef(MI.getOperand(0).getReg());
			addSrcOperand(MIB, src);
			MIB.addImm(src.offsetOfUse);
			MIB.addImm(src.widthOfUse);
			Observer.changedInstr(newMI);
		}
	} else {
		// we must build HWTFPGA_MERGE_VALUE for members
		Builder.setInstrAndDebugLoc(MI);
		auto currentInsertionPoint = Builder.getInsertPt();
		auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES);
		Observer.changingInstr(*MIB.getInstr());
		MIB.addDef(MI.getOperand(0).getReg());

		for (auto &src : concatMembers) {
			if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
				// use member directly
				addSrcOperand(MIB, src);
			} else {
				// slice the member using HWTFPGA_EXTRACT
				Builder.setInstrAndDebugLoc(MI);
				Builder.setInsertPt(*MI.getParent(), --currentInsertionPoint);
				auto memberMIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
				Observer.changingInstr(*memberMIB.getInstr());

				// $dst $src $offset $dstWidth
				Register memberReg = MRI.createVirtualRegister(
						&HwtFpga::anyregclsRegClass);
				memberMIB.addDef(memberReg, MI.getFlags());
				addSrcOperand(memberMIB, src);
				memberMIB.addImm(src.offsetOfUse);
				memberMIB.addImm(src.widthOfUse);
				Observer.changedInstr(*memberMIB.getInstr());

				MIB.addReg(memberReg);
			}
		}
		for (auto &src : concatMembers) {
			MIB.addImm(src.widthOfUse);
		}
		Observer.changedInstr(*MIB.getInstr());
	}

	MI.eraseFromParent();
}

bool HwtFpgaCombinerHelper::matchIsExtractOnConstShift(llvm::MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_EXTRACT);
	auto _src = MI.getOperand(1);
	if (_src.isReg()) {
		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			auto* srcInstr = src->getParent();
			auto opc = srcInstr->getOpcode();
			switch(opc) {
			case HwtFpga::HWTFPGA_SHL:
			//case HwtFpga::HWTFPGA_ASHR:
			//case HwtFpga::HWTFPGA_LSHR:
				return srcInstr->getOperand(2).isCImm();
			default:
				return false;
			};
		}
	}
	return false;
}

void HwtFpgaCombinerHelper::rewriteExtractOnConstShift(
		llvm::MachineInstr &MI) {
	auto *src = MRI.getOneDef(MI.getOperand(1).getReg());
	MachineInstr *srcInstr = src->getParent();
	auto srcValMO = srcInstr->getOperand(1);
	uint64_t offset = MI.getOperand(2).getImm();
	uint64_t shAmount = srcInstr->getOperand(2).getCImm()->getZExtValue();
	uint64_t resWidth = MI.getOperand(3).getImm();
	auto opc = srcInstr->getOpcode();
	switch (opc) {
	case HwtFpga::HWTFPGA_SHL: {
		assert(offset >= shAmount);
		offset -= shAmount;
		Builder.setInstrAndDebugLoc(MI);
		auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
		Observer.changingInstr(*MIB.getInstr());

		MIB.addDef(MI.getOperand(0).getReg());
		MIB.add(srcValMO);
		MIB.addImm(offset);
		MIB.addImm(resWidth);
		Observer.changedInstr(*MIB.getInstr());

		break;
	}
	//case HwtFpga::HWTFPGA_ASHR:
	//case HwtFpga::HWTFPGA_LSHR:
	//	return srcInstr->getOperand(2).isCImm();
	default:
		llvm_unreachable("This should have been checked before");
	};

	MI.eraseFromParent();
}

}
