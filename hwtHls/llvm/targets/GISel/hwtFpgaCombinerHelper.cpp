#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>

namespace llvm {

bool HwtFpgaCombinerHelper::isUndefOperand(const MachineOperand &MO) {
	if (MO.isReg()) {
		return (MO.isUndef()
				|| getOpcodeDef(TargetOpcode::G_IMPLICIT_DEF, MO.getReg(), MRI)
				|| getOpcodeDef(TargetOpcode::IMPLICIT_DEF, MO.getReg(), MRI));
	}
	return false;
}

MachineInstr* HwtFpgaCombinerHelper::getOpcodeDef(unsigned Opcode, Register Reg,
		const MachineRegisterInfo &MRI) {
	MachineInstr *DefMI = getDefIgnoringCopies(Reg, MRI);
	if (DefMI == nullptr) {
		auto DefMO = MRI.getOneDef(Reg);
		if (DefMO) {
			DefMI = DefMO->getParent(); // added because getDefIgnoringCopies fails for untyped registers
		}
	}
	return DefMI && DefMI->getOpcode() == Opcode ? DefMI : nullptr;
}

bool HwtFpgaCombinerHelper::matchAnyExplicitUseIsUndef(MachineInstr &MI) {
	return any_of(MI.explicit_uses(), [this](const MachineOperand &MO) {
		return isUndefOperand(MO);
	});
}

//bool HwtFpgaCombinerHelper::replaceInstWithUndefNonGeneric(MachineInstr &MI) {
//  assert(MI.getNumDefs() == 1 && "Expected only one def?");
//  Builder.setInstr(MI);
//  Builder.buildInstr(TargetOpcode::IMPLICIT_DEF, {MI.getOperand(0)}, {});
//  MI.eraseFromParent();
//  return true;
//}

bool HwtFpgaCombinerHelper::hashOnlyConstUses(llvm::MachineInstr &MI) {
	for (auto &op : MI.uses()) {
		if (op.isReg())
			return false;
	}
	return true;
}

bool HwtFpgaCombinerHelper::rewriteConstExtract(llvm::MachineInstr &MI) {
	auto _v = MI.getOperand(1).getCImm();
	const APInt &v = _v->getValue();
	auto bitPosition = MI.getOperand(2).getImm();
	auto numBits = MI.getOperand(3).getImm();
	replaceInstWithConstant(MI, v.extractBits(numBits, bitPosition));
	return true;
}

bool HwtFpgaCombinerHelper::hasG_CONSTANTasUse(llvm::MachineInstr &MI) {
	auto &Context = MI.getMF()->getFunction().getContext();
	for (auto &MO : MI.uses()) {
		if (hwtHls::HwtFpgaInstructionSelector::machineOperandTryGetConst(
				Context, MRI, MO)) {
			return true;
		}
	}
	return false;
}

bool HwtFpgaCombinerHelper::rewriteG_CONSTANTasUseAsCImm(
		llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	auto MIB = Builder.buildInstr(MI.getOpcode());
	auto &newMI = *MIB.getInstr();
	Observer.changingInstr(newMI);
	hwtHls::HwtFpgaInstructionSelector::selectInstrArgs(MI, MIB,
			MI.getOperand(0).isDef());
	Observer.changedInstr(newMI);
	MI.eraseFromParent();
	return true;
}

bool HwtFpgaCombinerHelper::rewriteConstMergeValues(llvm::MachineInstr &MI) {
	// $dst $src{N}, $width{N} (lowest bits first)
	// [todo] check for undefs
	uint64_t srcCnt = (MI.getNumOperands() - 1) / 2;
	uint64_t totalWidth = 0;
	for (unsigned i = 0; i < srcCnt; ++i) {
		uint64_t width = MI.getOperand(1 + srcCnt + i).getImm();
		totalWidth += width;
	}
	APInt res(totalWidth, 0);
	for (int i = srcCnt - 1; i >= 0; --i) {
		uint64_t width = MI.getOperand(1 + srcCnt + i).getImm();
		res <<= width;
		APInt v = MI.getOperand(1 + i).getCImm()->getValue().zext(totalWidth);
		res |= v;
	}
	replaceInstWithConstant(MI, res);
	return true;
}

bool HwtFpgaCombinerHelper::matchAllOnesConstantOp(
		const llvm::MachineOperand &MOP) {
	if (MOP.isCImm()) {
		return MOP.getCImm()->getValue().isAllOnes();
	}
	if (!MOP.isReg()) {
		return false;
	}
	auto *MI = MRI.getVRegDef(MOP.getReg());
	auto MaybeCst = isConstantOrConstantSplatVector(*MI, MRI);
	return MaybeCst.has_value() && MaybeCst->isAllOnes();
}

bool HwtFpgaCombinerHelper::matchOperandIsAllOnes(llvm::MachineInstr &MI,
		unsigned OpIdx) {
	return matchAllOnesConstantOp(MI.getOperand(OpIdx))
			&& (MI.getOperand(OpIdx).isCImm()
					|| canReplaceReg(MI.getOperand(0).getReg(),
							MI.getOperand(OpIdx).getReg(), MRI));
}

bool HwtFpgaCombinerHelper::rewriteXorToNot(llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	Builder.buildInstr(HwtFpga::HWTFPGA_NOT, { MI.getOperand(0) },
			{ MI.getOperand(1) }, MI.getFlags());
	MI.eraseFromParent();
	return true;
}

bool HwtFpgaCombinerHelper::rewriteConstBinOp(llvm::MachineInstr &MI,
		std::function<APInt(const APInt&, const APInt&)> fn) {
	auto _v = MI.getOperand(1).getCImm();
	const APInt &a = _v->getValue();
	const APInt &b = MI.getOperand(2).getCImm()->getValue();
	replaceInstWithConstant(MI, fn(a, b));
	return true;
}

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

inline bool collectConcatMembersAsItIs(llvm::MachineOperand &MIOp,
		std::vector<HwtFpgaCombinerHelper::ConcatMember> &members,
		uint64_t mainOffset, uint64_t mainWidth, uint64_t &currentOffset,
		uint64_t offsetOfIRes, uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	// take slice from this instruction as it is
	uint64_t bitsToTake = std::min(widthOfIRes, mainEnd - currentOffset);
	currentOffset += widthOfIRes;
	if (currentOffset < mainOffset) {
		// skip prefix
		return true;
	} else {
		members.push_back(HwtFpgaCombinerHelper::ConcatMember { MIOp,
				offsetOfIRes, widthOfIRes, bitsToTake });
		return false;
	}
}

bool HwtFpgaCombinerHelper::collectConcatMembers(llvm::MachineOperand &MIOp,
		std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
		uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	MachineInstr &MI = *MIOp.getParent();
	switch (MI.getOpcode()) {
	case HwtFpga::HWTFPGA_MERGE_VALUES: {
		//  $dst $src{N}, $width{N} (lowest bits first)
		uint64_t srcCnt = (MI.getNumOperands() - 1) / 2;
		bool didReduce = false;
		for (unsigned i = 0; i < srcCnt; ++i) {
			// [todo] check if thisMemberOffset is computed correctly for more than 2 operands
			uint64_t thisMemberOffset = 0;
			uint64_t width = MI.getOperand(1 + srcCnt + i).getImm();
			if (offsetOfIRes) {
				if (offsetOfIRes > width) {
					thisMemberOffset = width;
					offsetOfIRes -= width;
					width = 0;
				} else {
					thisMemberOffset = offsetOfIRes;
					width -= offsetOfIRes;
					offsetOfIRes = 0;
				}
			}
			if (currentOffset + width < mainOffset || width == 0) {
				didReduce = true;
				currentOffset += width;
				// skipping the unused prefix
			} else {
				auto &op = MI.getOperand(1 + i);
				MachineOperand *src = nullptr;
				if (op.isReg())
					src = MRI.getOneDef(op.getReg());
				if (src) {
					// can look trough
					didReduce |= collectConcatMembers(*src, members, mainOffset,
							mainWidth, currentOffset, thisMemberOffset, width);
				} else {
					// must take as it is
					collectConcatMembersAsItIs(op, members, mainOffset,
							mainWidth, currentOffset, thisMemberOffset, width);
				}
			}
			if (currentOffset >= mainEnd) {
				// we do not care about successors because parent EXTRACT does not select them
				didReduce |= i != srcCnt;
				break;
			}
		}
		return didReduce;
	}
	case HwtFpga::HWTFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		uint64_t subSliceOffset = MI.getOperand(2).getImm();
		uint64_t subSliceResWidth = MI.getOperand(3).getImm();
		subSliceOffset += offsetOfIRes;
		if (widthOfIRes > subSliceResWidth) {
			errs() << MI << " widthOfIRes:" << widthOfIRes << "\n";
			llvm_unreachable(
					"HWTFPGA_EXTRACT provides value of less bits than expected");
		}

		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			// look trough the source operand of this extract instruction
			bool mayContainOtherSlicesAndConcats = false;
			switch (src->getParent()->getOpcode()) {
			case HwtFpga::HWTFPGA_MERGE_VALUES:
			case HwtFpga::HWTFPGA_EXTRACT:
				mayContainOtherSlicesAndConcats = true;
				break;
			}
			if (mayContainOtherSlicesAndConcats) {
				bool didReduce = collectConcatMembers(*src, members, mainOffset,
						mainWidth, currentOffset, subSliceOffset,
						subSliceResWidth); // [fixme] subSliceResWidth is not correct it should be the width of src but it is unknown at this point
				assert(members.size());
				const auto &lastAdded = members.back();
				didReduce |= &lastAdded.op != src;
				return didReduce;
			}
		}

		break;
	}
	}
	return collectConcatMembersAsItIs(MIOp, members, mainOffset, mainWidth,
			currentOffset, offsetOfIRes, widthOfIRes);
}

void addSrcOperand(MachineInstrBuilder &MIB,
		HwtFpgaCombinerHelper::ConcatMember &src) {
	if (src.op.isReg() && src.op.isDef())
		MIB.addUse(src.op.getReg()); // convert def to use
	else {
		MIB.add(src.op);
	}
}

bool HwtFpgaCombinerHelper::rewriteExtractOnMergeValues(
		llvm::MachineInstr &MI) {
	// MI.operands() == $dst $src $offset $dstWidth
	std::vector<ConcatMember> concatMembers;
	//uint64_t mainOffset = MI.getOperand(2).getImm();
	uint64_t mainWidth = MI.getOperand(3).getImm();
	uint64_t currentOffset = 0;
	bool didReduce = collectConcatMembers(MI.getOperand(0), concatMembers, 0,
			mainWidth, currentOffset, 0, mainWidth);
	if (!didReduce)
		return false;
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
			// $dst $src $offset $dstWidth
			MIB.addDef(MI.getOperand(0).getReg());
			addSrcOperand(MIB, src);
			MIB.addImm(src.offsetOfUse);
			MIB.addImm(src.widthOfUse);
		}
	} else {
		// we must build HWTFPGA_MERGE_VALUE for members
		Builder.setInstrAndDebugLoc(MI);
		auto currentInsertionPoint = Builder.getInsertPt();
		auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MERGE_VALUES);
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
				// $dst $src $offset $dstWidth
				Register memberReg = MRI.createVirtualRegister(
						&HwtFpga::anyregclsRegClass);
				memberMIB.addDef(memberReg, MI.getFlags());
				addSrcOperand(memberMIB, src);
				memberMIB.addImm(src.offsetOfUse);
				memberMIB.addImm(src.widthOfUse);
				MIB.addReg(memberReg);
			}
		}
		for (auto &src : concatMembers) {
			MIB.addImm(src.widthOfUse);
		}
	}
	MI.eraseFromParent();
	return true;
}

bool HwtFpgaCombinerHelper::matchCmpToMsbCheck(llvm::MachineInstr &MI,
		BuildFnTy &rewriteFn) {
	auto Pred = static_cast<CmpInst::Predicate>(MI.getOperand(1).getPredicate());
	auto LHS = MI.getOperand(2);
	auto RHS = MI.getOperand(3);

	if ((Pred == CmpInst::Predicate::ICMP_SGE && RHS.isCImm()
			&& RHS.getCImm()->getValue().isZero())
			|| (Pred == CmpInst::Predicate::ICMP_SGT
					&& matchAllOnesConstantOp(RHS))) {
		// (SGE x,  0) -> NOT x.msb
		// (SGT x, -1) -> NOT x.msb
		unsigned bitWidth = RHS.getCImm()->getType()->getIntegerBitWidth();
		Register Dst = MI.getOperand(0).getReg();
		hwtHls::CImmOrReg _LHS(LHS);
		rewriteFn = [bitWidth, Dst, _LHS, this](MachineIRBuilder &builder) {
			// msbReg = x.MSB
			Register msbReg = buildMsbGet(builder, Observer, _LHS, bitWidth,
					std::nullopt);
			// res = not msbReg
			builder.buildInstr(HwtFpga::HWTFPGA_NOT, { Dst }, { msbReg });
		};
		return true;
	} else if ((Pred == CmpInst::Predicate::ICMP_SLT && RHS.isCImm()
			&& RHS.getCImm()->getValue().isZero())
			|| (Pred == CmpInst::Predicate::ICMP_SGT
					&& matchAllOnesConstantOp(RHS))) {
		// (SLT x,  0) -> x.msb
		// (SGT x, -1) -> x.msb
		unsigned bitWidth = RHS.getCImm()->getType()->getIntegerBitWidth();
		Register Dst = MI.getOperand(0).getReg();
		hwtHls::CImmOrReg _LHS(LHS);
		rewriteFn = [bitWidth, Dst, _LHS, this](MachineIRBuilder &builder) {
			// res = msbReg = x.MSB
			hwtHls::buildMsbGet(builder, Observer, _LHS, bitWidth, Dst);
		};
		return true;
	}
	return false;
}

bool HwtFpgaCombinerHelper::matchConstCmpConstAdd(llvm::MachineInstr &MI,
		BuildFnTy &rewriteFn) {
	assert(
			MI.getOpcode() == TargetOpcode::G_ICMP
					|| MI.getOpcode() == HwtFpga::HWTFPGA_ICMP);
	auto Pred = static_cast<CmpInst::Predicate>(MI.getOperand(1).getPredicate());
	const auto LHS = MI.getOperand(2);
	const auto RHS = MI.getOperand(3);
	if (Pred == CmpInst::Predicate::ICMP_EQ
			|| Pred == CmpInst::Predicate::ICMP_NE) { // [todo] rest of the predicates
		if (LHS.isReg() && RHS.isCImm()) {
			MachineOperand *_LHS = MRI.getOneDef(LHS.getReg());
			if (!_LHS)
				return false;
			auto lhsOpcode = _LHS->getParent()->getOpcode();
			if (lhsOpcode == TargetOpcode::G_ADD
					|| lhsOpcode == HwtFpga::HWTFPGA_ADD
					|| lhsOpcode == TargetOpcode::G_SUB
					|| lhsOpcode == HwtFpga::HWTFPGA_SUB) {
				const auto LHS_LHS = _LHS->getParent()->getOperand(1);
				const auto LHS_RHS = _LHS->getParent()->getOperand(2);
				if (LHS_RHS.isCImm()) {
					// [fixme] assert that add/sub operands are not modified between  until icmp instr.
					APInt lhsVal = RHS.getCImm()->getValue(); // original value which was compared with
					auto lhsRhsVal = LHS_RHS.getCImm()->getValue(); // the const value used in add/sub
					switch (lhsOpcode) {
					case HwtFpga::HWTFPGA_ADD:
					case TargetOpcode::G_ADD:
						lhsVal -= lhsRhsVal;
						break;
					case HwtFpga::HWTFPGA_SUB:
					case TargetOpcode::G_SUB:
						lhsVal += lhsRhsVal;
						break;
					}

					hwtHls::CImmOrReg newLHS(LHS_LHS);
					ConstantInt *newRhs = ConstantInt::get(
							Builder.getMF().getFunction().getContext(), lhsVal);
					Register Dst = MI.getOperand(0).getReg();
					rewriteFn = [Dst, Pred, newLHS, newRhs, this](
							MachineIRBuilder &builder) {
						auto MIB = builder.buildInstr(TargetOpcode::G_ICMP);
						MIB.addDef(Dst).addPredicate(Pred);
						newLHS.addAsUse(MIB);
						MIB.addCImm(newRhs);
					};
					return true;
				}
			}
		}
	}
	return false;
}

bool HwtFpgaCombinerHelper::genericOpcodeToHwtfpga(llvm::MachineInstr &MI) {
	unsigned newOpc;
	switch (MI.getOpcode()) {
	case TargetOpcode::G_ADD:
		newOpc = HwtFpga::HWTFPGA_ADD;
		break;
	case TargetOpcode::G_AND:
		newOpc = HwtFpga::HWTFPGA_AND;
		break;
	case TargetOpcode::G_BR:
		newOpc = HwtFpga::HWTFPGA_BR;
		break;
	case TargetOpcode::G_BRCOND:
		newOpc = HwtFpga::HWTFPGA_BRCOND;
		break;
	case TargetOpcode::G_ICMP:
		newOpc = HwtFpga::HWTFPGA_ICMP;
		break;
	case TargetOpcode::G_IMPLICIT_DEF:
		newOpc = HwtFpga::IMPLICIT_DEF;
		break;
	case TargetOpcode::G_GLOBAL_VALUE:
		newOpc = HwtFpga::HWTFPGA_GLOBAL_VALUE;
		break;
	case TargetOpcode::G_MUL:
		newOpc = HwtFpga::HWTFPGA_MUL;
		break;
	case TargetOpcode::G_UDIV:
		newOpc = HwtFpga::HWTFPGA_UDIV;
		break;
	case TargetOpcode::G_SDIV:
		newOpc = HwtFpga::HWTFPGA_SDIV;
		break;
	case TargetOpcode::G_UREM:
		newOpc = HwtFpga::HWTFPGA_UREM;
		break;
	case TargetOpcode::G_SREM:
		newOpc = HwtFpga::HWTFPGA_SREM;
		break;
	case TargetOpcode::G_OR:
		newOpc = HwtFpga::HWTFPGA_OR;
		break;
	case TargetOpcode::G_SUB:
		newOpc = HwtFpga::HWTFPGA_SUB;
		break;
	case TargetOpcode::G_XOR:
		newOpc = HwtFpga::HWTFPGA_XOR;
		break;
	default:
		llvm_unreachable(
				"All cases should be covered in this switch in generic_opcode_to_hwtfpga");
	}
	replaceOpcodeWith(MI, newOpc);
	return true;
}

bool HwtFpgaCombinerHelper::matchConstMergeValues(llvm::MachineInstr &MI,
		llvm::APInt &replacement) {
	auto values = hwtHls::MERGE_VALUES_iter_values(MI);
	auto widths = hwtHls::MERGE_VALUES_iter_widths(MI);
	size_t resultWidth = hwtHls::MERGE_VALUES_getResultWidth(MI);
	APInt resTmp(resultWidth, 0);
	auto widthMo = widths.begin();
	size_t curOffset = 0;
	for (llvm::MachineOperand &valMO : values) {
		if (valMO.isCImm()) {
			resTmp |= valMO.getCImm()->getValue().zext(resultWidth)
					<< curOffset;
		} else if (isUndefOperand(valMO)) {
			// [todo] now replacing undef with 0 but we should preserve validity mask
		} else {
			// not a constant or undef, we can not replace
			return false;
		}
		curOffset += widthMo->getImm();
		++widthMo;
	}
	replacement = resTmp;
	return true;
}

bool HwtFpgaCombinerHelper::rewriteConstMergeValues(llvm::MachineInstr &MI,
		const llvm::APInt &replacement) {
	replaceInstWithConstant(MI, replacement);
	return true;
}

bool HwtFpgaCombinerHelper::matchTrivialInstrDuplication(
		llvm::MachineInstr &MI) {
	assert(MI.getNumDefs() == 1);
	auto NextInst = MI.getNextNode();
	if (!NextInst || NextInst->getOpcode() != MI.getOpcode()
			|| NextInst->getNumOperands() != MI.getNumOperands()) {
		return false;
	}
	// chechk def operands
	for (auto I0 : { &MI, NextInst }) {
		auto I1 = I0 == &MI ? NextInst : &MI;
		for (auto def : I0->defs()) {
			if (!MRI.hasOneDef(def.getReg())) {
				return false; // result register used on multiple places, the check for liveness would be required
			} else if (def.isDead()) {
				return false; // this is subject to DCE, skip this
			} else if (I1->readsRegister(def.getReg())) {
				return false; // The instruction is using the result of other
			}
		}
	}
	// check if use operands are the same
	for (const auto [U0, U1] : zip(MI.uses(), NextInst->uses())) {
		if (U0.isReg() && U1.isReg() && U0.getReg() == U1.getReg()) {
			continue;
		} else if (U0.isCImm() && U1.isCImm() && U0.getCImm() == U1.getCImm())
			continue;
		return false;
	}
	return true;
}

bool HwtFpgaCombinerHelper::rewriteTrivialInstrDuplication(
		llvm::MachineInstr &MI) {
	assert(MI.getNumDefs() == 1);
	auto def0 = MI.getOperand(0);
	assert(def0.isDef());
	auto *OtherMI = MI.getNextNode();
	auto def1 = OtherMI->getOperand(0);
	assert(def1.isDef());
	if (def0.getReg() != def1.getReg())
		MRI.replaceRegWith(def0.getReg(), def1.getReg());

	MI.eraseFromParent();
	return true;
}

}
