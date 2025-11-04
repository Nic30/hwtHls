#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelValueTracking.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

namespace llvm {

bool HwtFpgaCombinerHelper::matchIsExtractOnMergeValues(llvm::MachineInstr &MI,
		std::vector<ConcatMember> &concatMembers) {
	concatMembers.clear();
	auto &_src = MI.getOperand(1);
	if (!_src.isReg())
		return false;
	auto *src = MRI.getOneDef(MI.getOperand(1).getReg());
	if (!src)
		return false;

	if (src->getParent()->getOpcode() != HwtFpga::HWTFPGA_MERGE_VALUES)
		return false;

	auto ExtractOps = hwtHls::HWTFPGA_EXTRACTOptions::get(MI);
	uint64_t mainWidth = ExtractOps.dstWidth;
	uint64_t currentOffset = 0;
	auto DstMO = MI.getOperand(0);
	bool didReduce = collectConcatMembers(DstMO, concatMembers, 0, mainWidth,
			currentOffset, 0, mainWidth, mainWidth);
	if (!didReduce)
		return false;
	if (concatMembers.size() == 1) {
		auto newSrc = concatMembers.back();
		if (newSrc.existingSlice == &MI)
			return false;
		if (matchEqualDefs(newSrc.op, *src)) {
			return false; // this was resolved to same instruction
		}
	}
	return true;
}

void addSrcOperand(MachineInstrBuilder &MIB,
		const HwtFpgaCombinerHelper::ConcatMember &src) {
	if (src.existingSlice) {
		MIB.addUse(src.existingSlice->getOperand(0).getReg()); // convert dst HWTFPGA_EXTRACT def to use
	} else if (src.op.isReg() && src.op.isDef())
		MIB.addUse(src.op.getReg()); // convert def to use
	else {
		assert(src.op.isReg() || src.op.isCImm());
		MIB.add(src.op);
	}
}

void addSrcOperand(MachineInstrBuilder &MIB, MachineOperand &src) {
	if (src.isReg() && src.isDef())
		MIB.addUse(src.getReg()); // convert def to use
	else {
		assert(src.isReg() || src.isCImm());
		MIB.add(src);
	}
}

void HwtFpgaCombinerHelper::rewriteExtractOnMergeValues(llvm::MachineInstr &MI,
		const std::vector<ConcatMember> &concatMembers) {
	// MI.operands() == $dst $src $srcWidth $offset $dstWidth
	auto DstMO = MI.getOperand(0);
	assert(
			concatMembers.size()
					&& "There must be something which EXTRACT selects");

	if (concatMembers.size() == 1) {
		auto &src = concatMembers.back();
		// we may be able to use item directly of we may build an EXTRACT
		if (src.existingSlice) {
			Builder.setInstr(MI);
			auto sliceDstOp = src.existingSlice->getOperand(0);
			if (!MRI.hasOneDef(sliceDstOp.getReg())) {
				// in the case that there are multiple defs we create backup copy after slice instruction
				hwtHls::MachineInsertPointGuard(Builder,
						*src.existingSlice->getParent(),
						src.existingSlice->getNextNode());
				auto cpMIB = buildHwtFpgaCopy(sliceDstOp);
				sliceDstOp = cpMIB.getInstr()->getOperand(0);
			}
			buildHwtFpgaCopy(DstMO, sliceDstOp);
		} else if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
			// whole value of src is used, use it directly
			if (src.op.isReg()) {
				Builder.setInstr(
						*const_cast<MachineInstr*>(src.op.getParent())->getNextNode());
				bool dstHasOneDef = MRI.getOneDef(DstMO.getReg());
				if (dstHasOneDef) {
					buildHwtFpgaCopy(DstMO, src.op);
					if (src.op.isUndef()) {
						for (auto &U : MRI.use_operands(src.op.getReg())) {
							U.setIsUndef();
						}
					}
				} else {
					auto tmpCp = buildHwtFpgaCopy(src.op);
					Builder.setInstr(MI);
					buildHwtFpgaCopy(DstMO, tmpCp.getInstr()->getOperand(0));
				}
				//auto *srcDef = MRI.getOneDef(src.op.getReg());
				//assert(
				//		srcDef
				//				&& "src must have 1 def because otherwise this should not have been matched");
				//replaceRegWith(MRI, DstMO.getReg(), src.op.getReg());
				//	//if (MI.getParent() != src.op.getParent()->getParent() || MI.getIterator())
				//	assert(MI.getParent() == src.op.getParent()->getParent());
				//	// must create extract at the place of src def
				//	if (dstHasOneDef) {
				//		buildHwtFpgaCopy(DstMO, src.op);
				//	} else if (srcHasOneDef) {
				//
				//	}

			} else if (src.op.isCImm()) {
				Builder.setInstrAndDebugLoc(MI);
				Register srcReg = MRI.createVirtualRegister(
						&HwtFpga::anyregclsRegClass);
				const ConstantInt *C = src.constOverride;
				if (!C) {
					C = src.op.getCImm();
				}
				auto width = C->getBitWidth();
				MRI.setType(srcReg, LLT::scalar(width));
				Builder.buildConstant(srcReg, *C);
				replaceRegWith(MRI, DstMO.getReg(), srcReg);
			} else {
				llvm_unreachable(
						"HwtFpgaCombinerHelper::rewriteExtractOnMergeValues unexpected type of src operand");
			}
		} else {
			assert(src.op.isReg()); // :note: constants should have been merged and offsetOfUse, width, widthOfUse updated so previous case
			// branch should have been taken if this is const
			// :attention: HWTFPGA_EXTRACT must be constructed in the place where
			//   src.op was originally used, because it can be redefined on the way to MI
			Builder.setInstr(
					*const_cast<MachineInstr*>(src.op.getParent())->getNextNode());
			// auto *srcDef = MRI.getOneDef(src.op.getReg());
			MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
			auto &newMI = *MIB.getInstr();
			Observer.changingInstr(newMI);
			// $dst $src $srcWidth $offset $dstWidth
			MIB.addDef(DstMO.getReg());
			// this would break CSEInfo llvm-18
			// MRI.setType(DstMO.getReg(), LLT::scalar(src.widthOfUse));
			addSrcOperand(MIB, src);
			//if (src.op.isReg()) {
			//  // this would result in broken CSEMap llvm-18
			//	MRI.setType(src.op.getReg(), LLT::scalar(src.width));
			//}
			assert(src.width >= src.offsetOfUse + src.widthOfUse);
			MIB.addImm(src.width);
			MIB.addImm(src.offsetOfUse);
			MIB.addImm(src.widthOfUse);
			assert(newMI.getNumExplicitOperands() == 5);
			Observer.changedInstr(newMI);
		}
	} else {
		// we must build HWTFPGA_MERGE_VALUE for members
		size_t resWidth = 0;
		SmallVector<MachineOperand> concatOps;
		for (auto &src : concatMembers) {
			if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
				// use member directly
				if (src.op.isReg()) {
					if (MRI.getOneDef(src.op.getReg())) {
						concatOps.push_back(src.op);
					} else {
						// create copy in the place where the src.op was used to backup its original value
						auto srcCp = buildHwtFpgaCopy(src.op);
						concatOps.push_back(srcCp.getInstr()->getOperand(0));
					}

#ifndef NDEBUG
					auto OpTy = MRI.getType(src.op.getReg());
					if (OpTy.isValid()) {
						assert(OpTy.getScalarSizeInBits() == src.widthOfUse);
					}
#endif
				} else {
					if (src.constOverride) {
						concatOps.push_back(
								MachineOperand::CreateCImm(src.constOverride));
					} else {
						concatOps.push_back(src.op);
					}
				}

			} else {
				if (src.existingSlice) {
					concatOps.push_back(src.existingSlice->getOperand(0));
				} else {
					// slice the member using HWTFPGA_EXTRACT
					Builder.setInstr(
							*const_cast<MachineInstr*>(src.op.getParent())->getNextNode());
					MachineInstrBuilder memberMIB = Builder.buildInstr(
							HwtFpga::HWTFPGA_EXTRACT);
					Observer.changingInstr(*memberMIB.getInstr());

					// $dst $src $offset $dstWidth
					Register memberReg = MRI.createVirtualRegister(
							&HwtFpga::anyregclsRegClass);
					MRI.setType(memberReg, LLT::scalar(src.widthOfUse));
					memberMIB.addDef(memberReg, MI.getFlags());
					addSrcOperand(memberMIB, src);
					memberMIB.addImm(src.width);
					memberMIB.addImm(src.offsetOfUse);
					memberMIB.addImm(src.widthOfUse);

					assert(memberMIB.getInstr()->getNumExplicitOperands() == 5);
					Observer.changedInstr(*memberMIB.getInstr());
					concatOps.push_back(memberMIB.getInstr()->getOperand(0));
				}
			}
			resWidth += src.widthOfUse;
		}

		Builder.setInstrAndDebugLoc(MI);
		MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES);
		Observer.changingInstr(*MIB.getInstr());
		MIB.addDef(DstMO.getReg());
		assert(concatOps.size() == concatMembers.size());
		for (auto o : concatOps)
			addSrcOperand(MIB, o);
		for (auto &src : concatMembers) {
			MIB.addImm(src.widthOfUse);
		}
		auto dstTy = MRI.getType(DstMO.getReg());
		if (dstTy.isValid()) {
			assert(dstTy.getScalarSizeInBits() == resWidth);
		} else {
			// this would break CSEInfo in llvm-18
			// MRI.setType(DstMO.getReg(), LLT::scalar(resWidth));
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
			auto *srcInstr = src->getParent();
			auto opc = srcInstr->getOpcode();
			switch (opc) {
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

void HwtFpgaCombinerHelper::rewriteExtractOnConstShift(llvm::MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_EXTRACT);
	auto *src = MRI.getOneDef(MI.getOperand(1).getReg());
	MachineInstr *srcInstr = src->getParent();
	auto srcValMO = srcInstr->getOperand(1);
	auto extractOpts = hwtHls::HWTFPGA_EXTRACTOptions::get(MI);
	uint64_t offset = extractOpts.offset;
	uint64_t shAmount = srcInstr->getOperand(2).getCImm()->getZExtValue();
	switch (srcInstr->getOpcode()) {
	case HwtFpga::HWTFPGA_SHL: {
		assert(offset >= shAmount);
		offset -= shAmount;
		Builder.setInstrAndDebugLoc(MI);
		MachineInstrBuilder MIB = Builder.buildInstr(HwtFpga::HWTFPGA_EXTRACT);
		Observer.changingInstr(*MIB.getInstr());

		MIB.addDef(MI.getOperand(0).getReg());
		MIB.add(srcValMO);
		assert(extractOpts.srcWidth >= offset + extractOpts.dstWidth);
		MIB.addImm(extractOpts.srcWidth);
		MIB.addImm(offset);
		MIB.addImm(extractOpts.dstWidth);
		assert(MIB->getNumExplicitOperands() == 5);
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

bool HwtFpgaCombinerHelper::matchExtractOfSameWidth(llvm::MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_EXTRACT);
	auto _src = MI.getOperand(1);
	if (_src.isReg()) {
		auto extractArgs = hwtHls::HWTFPGA_EXTRACTOptions::get(MI);
		if (extractArgs.offset == 0
				&& extractArgs.srcWidth == extractArgs.dstWidth) {
			auto srcTy = MRI.getType(_src.getReg());
			return srcTy.isValid(); // return true only if type is set so the width of original register is not lost
		}

	}
	return false;
}

void HwtFpgaCombinerHelper::rewriteExtractOfSameWidthToCopy(
		llvm::MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_EXTRACT);
	Observer.changingInstr(MI);
	// HWTFPGA_EXTRACT $dst $src $srcWidth $offset $dstWidth
	// to  HWTFPGA_MUX $dst $src
	for (size_t i = 4; i > 1; --i)
		MI.removeOperand(i);
	MI.setDesc(Builder.getTII().get(HwtFpga::HWTFPGA_MUX));
	Observer.changedInstr(MI);
}

}
