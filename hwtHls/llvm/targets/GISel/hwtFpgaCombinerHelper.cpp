#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtilsInstrFns.h>

namespace llvm {

void HwtFpgaCombinerHelper::replaceInstWithUndef(llvm::MachineInstr &MI) {
	auto dstReg = MI.getOperand(0).getReg();
	auto dstTy = MRI.getType(dstReg);
	if (!dstTy.isValid()) {
		// attempt to backup register type
		if (MI.getOpcode() == HwtFpga::HWTFPGA_EXTRACT) {
			auto eOps = hwtHls::HWTFPGA_EXTRACTOptions::get(MI);
			Builder.buildInstr(HwtFpga::HWTFPGA_IMPLICIT_DEF,
					{ MI.getOperand(0) }, { eOps.dstWidth });
			MI.eraseFromParent();
			return;
		}
	}
	return llvm::CombinerHelper::replaceInstWithUndef(MI);
}

bool HwtFpgaCombinerHelper::matchEqualDefs(const MachineOperand &MO0,
		const MachineOperand &MO1) {
	if (&MO0 == &MO1)
		return true;
	else if ((MO0.isReg() && (MO0.isUndef() || !MRI.hasOneDef(MO0.getReg())))
			|| (MO1.isReg() && (MO1.isUndef() || !MRI.hasOneDef(MO1.getReg()))))
		return false;
	else if (MO0.isImm()) {
		if (MO1.isImm())
			return MO0.getImm() == MO1.getImm();
		else
			return false;
	} else if (MO0.isCImm()) {
		if (MO1.isCImm())
			return MO0.getCImm() == MO1.getCImm();
		else
			return false;
	}
	// :attention: assumes SSA
	return CombinerHelper::matchEqualDefs(MO0, MO1);
}

bool HwtFpgaCombinerHelper::matchEqualDefs(const MachineInstr &MI0,
		const MachineInstr &MI1, size_t opI) {
	auto &mo0 = MI0.getOperand(opI);
	auto &mo1 = MI1.getOperand(opI);
	return matchEqualDefs(mo0, mo1);
}

bool HwtFpgaCombinerHelper::isUndefOperand(const MachineOperand &MO) {
	if (MO.isReg()) {
		return (MO.isUndef()
				|| getOpcodeDef(HwtFpga::HWTFPGA_IMPLICIT_DEF, MO.getReg(), MRI)
				|| getOpcodeDef(TargetOpcode::G_IMPLICIT_DEF, MO.getReg(), MRI)
				|| getOpcodeDef(TargetOpcode::IMPLICIT_DEF, MO.getReg(), MRI));
	}
	return false;
}

MachineInstr* HwtFpgaCombinerHelper::getOpcodeDef(unsigned Opcode, Register Reg,
		const MachineRegisterInfo &MRI) {
	if (!MRI.hasOneDef(Reg))
		return nullptr;

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

void HwtFpgaCombinerHelper::rewriteConstExtract(llvm::MachineInstr &MI) {
	auto _v = MI.getOperand(1).getCImm();
	const APInt &v = _v->getValue();
	auto extractOpt = hwtHls::HWTFPGA_EXTRACTOptions::get(MI);
	auto Dst = MI.getOperand(0).getReg();
	auto DstTy = MRI.getType(Dst);
	if (DstTy.isValid()) {
		assert(DstTy.getScalarSizeInBits() == extractOpt.dstWidth);
	} else {
		MRI.setType(Dst, LLT::scalar(extractOpt.dstWidth));
	}

	replaceInstWithConstant(MI,
			v.extractBits(extractOpt.dstWidth, extractOpt.offset));
}

bool HwtFpgaCombinerHelper::hasG_CONSTANTasUse(llvm::MachineInstr &MI) {
	return hasG_CONSTANTasUse(MRI, MI);
}
bool HwtFpgaCombinerHelper::hasG_CONSTANTasUse(MachineRegisterInfo &MRI,
		llvm::MachineInstr &MI) {
	auto &Context = MI.getMF()->getFunction().getContext();
	for (auto &MO : MI.uses()) {
		if (hwtHls::HwtFpgaInstructionSelector::machineOperandTryGetConst(
				Context, MRI, MO)) {
			return true;
		}
	}
	return false;
}

void HwtFpgaCombinerHelper::rewriteG_CONSTANTasUseAsCImm(
		MachineIRBuilder &Builder, GISelChangeObserver *Observer,
		llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	auto MIB = Builder.buildInstr(MI.getOpcode());
	auto &newMI = *MIB.getInstr();
	if (Observer)
		Observer->changingInstr(newMI);
	hwtHls::HwtFpgaInstructionSelector::selectInstrArgs(MI, MIB,
			MI.getOperand(0).isDef());
	if (Observer)
		Observer->changedInstr(newMI);
	MI.eraseFromParent();
}

void HwtFpgaCombinerHelper::rewriteG_CONSTANTasUseAsCImm(
		llvm::MachineInstr &MI) {
	rewriteG_CONSTANTasUseAsCImm(Builder, &Observer, MI);
}

void HwtFpgaCombinerHelper::rewriteConstMergeValues(llvm::MachineInstr &MI) {
	// $dst $src{N}, $width{N} (lowest bits first)
	// [todo] check for undefs
	uint64_t totalWidth = hwtHls::MERGE_VALUES_getResultWidth(MI);
	APInt res(totalWidth, 0);
	size_t offset = 0;
	for (const auto& [V, W] : hwtHls::MERGE_VALUES_iter_valuesWidthPairs(MI)) {
		APInt v = V.getCImm()->getValue().zext(totalWidth) << offset;
		res |= v;
		offset += W.getImm();
	}
	replaceInstWithConstant(MI, res);
}

bool HwtFpgaCombinerHelper::matchAllOnesConstantOp(
		const llvm::MachineOperand &MOP) {
	if (MOP.isCImm()) {
		return MOP.getCImm()->getValue().isAllOnes();
	}
	if (!MOP.isReg()) {
		return false;
	}
	if (auto *MI = MRI.getUniqueVRegDef(MOP.getReg())) {
		auto MaybeCst = isConstantOrConstantSplatVector(*MI, MRI);
		if (MaybeCst.has_value() && MaybeCst->isAllOnes())
			return true;
		if (MI->getOpcode() == HwtFpga::HWTFPGA_MUX
				&& MI->getNumExplicitOperands() == 2) {
			auto &_MOP = MI->getOperand(1);
			if (_MOP.isCImm()) {
				return _MOP.getCImm()->isAllOnesValue();
			}
			return false;
		}
	}
	return false;
}

bool HwtFpgaCombinerHelper::matchOperandIsAllOnes(llvm::MachineInstr &MI,
		unsigned OpIdx) {
	return matchAllOnesConstantOp(MI.getOperand(OpIdx))
			&& (MI.getOperand(OpIdx).isCImm()
					|| canReplaceReg(MI.getOperand(0).getReg(),
							MI.getOperand(OpIdx).getReg(), MRI));
}

void HwtFpgaCombinerHelper::rewriteXorToNot(llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	Builder.buildInstr(HwtFpga::HWTFPGA_NOT, { MI.getOperand(0) },
			{ MI.getOperand(1) }, MI.getFlags());
	MI.eraseFromParent();
}

void HwtFpgaCombinerHelper::rewriteConstBinOp(llvm::MachineInstr &MI,
		std::function<APInt(const APInt&, const APInt&)> fn) {
	auto _v = MI.getOperand(1).getCImm();
	const APInt &a = _v->getValue();
	const APInt &b = MI.getOperand(2).getCImm()->getValue();
	replaceInstWithConstant(MI, fn(a, b));
}

HwtFpgaCombinerHelper::ConcatMember::ConcatMember(const MachineOperand &op,
		uint64_t offsetOfUse, uint64_t width, uint64_t widthOfUse) :
		op(op), constOverride(nullptr), offsetOfUse(offsetOfUse), width(width), widthOfUse(
				widthOfUse), existingSlice(nullptr) {
	assert(width >= offsetOfUse + widthOfUse);
	if (op.isCImm()) {
		assert(width == op.getCImm()->getType()->getIntegerBitWidth());
		if (offsetOfUse != 0 || width != widthOfUse) {
			// extract targeted bits immediately
			auto C = op.getCImm();
			this->constOverride = ConstantInt::get(C->getContext(),
					C->getValue().extractBits(widthOfUse, offsetOfUse));
			this->width = widthOfUse;
			this->offsetOfUse = 0;
		}
	}
}

bool HwtFpgaCombinerHelper::collectConcatMembersAsItIs(
		llvm::MachineOperand &MIOp,
		std::vector<HwtFpgaCombinerHelper::ConcatMember> &members,
		uint64_t mainOffset, uint64_t mainWidth, uint64_t &mainOffsetCurrent,
		uint64_t MIOpOffset, uint64_t MIOpWidth, uint64_t MIOpSelectedWidth) {
	assert(mainOffsetCurrent < mainWidth);
	assert(MIOpSelectedWidth + MIOpOffset <= MIOpWidth);
	uint64_t mainEnd = mainOffset + mainWidth;
	// take slice from this instruction as it is
	uint64_t bitsToTake = std::min(MIOpSelectedWidth,
			mainEnd - mainOffsetCurrent);
	mainOffsetCurrent += bitsToTake;
	if (mainOffsetCurrent < mainOffset) {
		// skip prefix
		return true;
	} else {
		if (!members.empty()) {
			auto &last = members.back();
			if (last.op.isCImm()) {
				if (MIOp.isCImm()) {
					assert(last.offsetOfUse == 0);
					assert(last.widthOfUse == last.width);
					const ConstantInt *lastC;
					if (last.constOverride)
						lastC = last.constOverride;
					else
						lastC = last.op.getCImm();

					auto &Ctx = lastC->getContext();
					auto vL = lastC->getValue().extractBits(last.widthOfUse,
							last.offsetOfUse);
					auto vH = MIOp.getCImm()->getValue().extractBits(MIOpWidth,
							MIOpOffset);
					auto newV = vH.concat(vL);
					last.constOverride = ConstantInt::get(Ctx, newV);
					last.widthOfUse += bitsToTake;
					last.width += bitsToTake;
					last.existingSlice = nullptr;
					return true;
				}
			} else if (matchEqualDefs(last.op, MIOp)) {
				assert(
						last.width == MIOpWidth
								&& "The width of MIOp should always be the same");
				if (last.offsetOfUse + last.widthOfUse == MIOpOffset) {
					// merge 2 continuous slices to 1 wider
					last.widthOfUse += bitsToTake;
					last.existingSlice = nullptr;
					return true;
				}
			}
		}
		members.push_back(HwtFpgaCombinerHelper::ConcatMember { MIOp,
				MIOpOffset, MIOpWidth, bitsToTake });
		return false;
	}
}

// RegisterIsDefinedWithinRange
bool HwtFpgaCombinerHelper::collectConcatMembers(llvm::MachineOperand &MIOp,
		std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, uint64_t &mainOffsetCurrent, uint64_t MIOpOffset,
		uint64_t MIOpWidth, uint64_t MIOpSelectedWidth) {
	uint64_t mainEnd = mainOffset + mainWidth;
	MachineInstr &MI = *MIOp.getParent();
#ifndef NDEBUG
	assert(MIOpOffset < MIOpWidth);
	MachineRegisterInfo &MRI = MI.getParent()->getParent()->getRegInfo();
	auto MIOpTy = MRI.getType(MIOp.getReg());
	if (MIOpTy.isValid()) {
		assert(
				MIOpTy.getScalarSizeInBits() == MIOpWidth
						&& "Has enough bits to extract");
	}
#endif
	switch (MI.getOpcode()) {
	case HwtFpga::HWTFPGA_MERGE_VALUES: {
		//  $dst $src{N}, $width{N} (lowest bits first)
		uint64_t srcCnt = hwtHls::MERGE_VALUES_getSrcOperandCount(MI);
		bool didReduce = false;
		size_t valMOIndex = 0;
		for (const auto& [valMO, widthMO] : hwtHls::MERGE_VALUES_iter_valuesWidthPairs(
				MI)) {
			uint64_t valMOWidth = widthMO.getImm();
			uint64_t valMOWidthToExtract = valMOWidth;
			if (MIOpOffset > valMOWidth) {
				// this operand is entirely sliced out prefix
				MIOpOffset -= valMOWidth;
				valMOWidthToExtract = 0;
			} else {
				uint64_t thisMemberOffset = MIOpOffset;
				valMOWidthToExtract -= MIOpOffset;
				MIOpOffset = 0; // set to 0 for next item
				if (mainOffsetCurrent + valMOWidthToExtract < mainOffset
						|| valMOWidthToExtract == 0) {
					// skipping the entirely unused prefix
					didReduce = true;
					mainOffsetCurrent += valMOWidthToExtract;
				} else {
					MachineOperand *src = nullptr;
					if (valMO.isReg()) {
						src = MRI.getOneDef(valMO.getReg());
					}
					if (src) {
						// can look trough
						didReduce |= collectConcatMembers(*src, members,
								mainOffset, mainWidth, mainOffsetCurrent,
								thisMemberOffset, valMOWidth,
								valMOWidth - thisMemberOffset);
					} else {
						// must take as it is
						didReduce |= collectConcatMembersAsItIs(valMO, members,
								mainOffset, mainWidth, mainOffsetCurrent,
								thisMemberOffset, valMOWidth,
								valMOWidth - thisMemberOffset);
					}
				}
			}
			if (mainOffsetCurrent >= mainEnd) {
				// we do not care about successors because parent EXTRACT does not select them
				didReduce |= valMOIndex != srcCnt - 1;
				break;
			}
			valMOIndex++;
		}
		return didReduce;
	}
	case HwtFpga::HWTFPGA_EXTRACT: {
		// fit this is a HWTFPGA_EXTRACT try to use src operand instead
		auto subSlice = hwtHls::HWTFPGA_EXTRACTOptions::get(MI);
		if (subSlice.dstWidth >= MIOpSelectedWidth) {
			// selects only some bits from this slice
		} else {
			errs() << MI << " widthOfIRes:" << MIOpSelectedWidth
					<< " subSlice.dstWidth:" << subSlice.dstWidth << "\n";
			llvm_unreachable(
					"HWTFPGA_EXTRACT provides value of less bits than expected");
		}

		auto *extractSrc = MRI.getOneDef(MI.getOperand(1).getReg());
		if (!extractSrc)
			break; // we can not look on def of src because there are multiple defs,
		// we have to use use MIOp (HWTFPGA_EXTRACT dst) as is

		// look trough the source operand of this HWTFPGA_EXTRACT instruction
		// if src operand is extract or merge we drill down to find most primitive inputs
		bool mayContainOtherSlicesAndConcats = false;
		auto srcOpc = extractSrc->getParent()->getOpcode();
		switch (srcOpc) {
		case HwtFpga::HWTFPGA_MERGE_VALUES:
		case HwtFpga::HWTFPGA_EXTRACT:
			mayContainOtherSlicesAndConcats = true;
			break;
		}
		bool didReduce;
		{
			auto offset = subSlice.offset + MIOpOffset;
			auto dstWidth = std::min(MIOpSelectedWidth, subSlice.dstWidth);
			assert(offset + dstWidth <= subSlice.srcWidth);
			if (mayContainOtherSlicesAndConcats) {
				didReduce = collectConcatMembers(*extractSrc, members,
						mainOffset, mainWidth, mainOffsetCurrent, offset,
						subSlice.srcWidth, dstWidth);
			} else {
				didReduce = collectConcatMembersAsItIs(*extractSrc, members,
						mainOffset, mainWidth, mainOffsetCurrent, offset,
						subSlice.srcWidth, dstWidth);

			}
		}
		assert(members.size());
		auto &lastAdded = members.back();
		// :note: can not reuse existing slices as they are because, if we do that we wold not be able to merge items in members
		//        because we would not know that we should analyze this item again when resolving continuous slices
		if (matchEqualDefs(lastAdded.op, *extractSrc) && lastAdded.width != 1 // to discard [0] slices on 1b vectors
		&& lastAdded.offsetOfUse == subSlice.offset
				&& lastAdded.widthOfUse == subSlice.dstWidth) {
			// this would result in copy of this instruction, to prevent it, we use reuse existing instruction
			lastAdded.existingSlice = &MI;
		} else {
			didReduce = true;
		}
		return didReduce;
	}
	}
	// can not look trough instruction to find a source of bits
	return collectConcatMembersAsItIs(MIOp, members, mainOffset, mainWidth,
			mainOffsetCurrent, MIOpOffset, MIOpWidth, MIOpSelectedWidth);
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

void HwtFpgaCombinerHelper::rewriteGenericOpcodeToHwtFpga(
		llvm::MachineInstr &MI) {
	unsigned newOpc;
	bool addPredicate = false;
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
	case TargetOpcode::IMPLICIT_DEF:
	case TargetOpcode::G_IMPLICIT_DEF:
		newOpc = HwtFpga::HWTFPGA_IMPLICIT_DEF;
		break;
	case TargetOpcode::G_GLOBAL_VALUE:
		newOpc = HwtFpga::HWTFPGA_GLOBAL_VALUE;
		break;
	case TargetOpcode::G_MUL:
		newOpc = HwtFpga::HWTFPGA_MUL;
		break;
	case TargetOpcode::G_UDIV:
		newOpc = HwtFpga::HWTFPGA_UDIV;
		addPredicate = true;
		break;
	case TargetOpcode::G_SDIV:
		newOpc = HwtFpga::HWTFPGA_SDIV;
		addPredicate = true;
		break;
	case TargetOpcode::G_UREM:
		newOpc = HwtFpga::HWTFPGA_UREM;
		addPredicate = true;
		break;
	case TargetOpcode::G_SREM:
		newOpc = HwtFpga::HWTFPGA_SREM;
		addPredicate = true;
		break;
	case TargetOpcode::G_UDIVREM:
		newOpc = HwtFpga::HWTFPGA_UDIVREM;
		addPredicate = true;
		break;
	case TargetOpcode::G_SDIVREM:
		newOpc = HwtFpga::HWTFPGA_SDIVREM;
		addPredicate = true;
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

	case TargetOpcode::COPY:
	case TargetOpcode::G_FREEZE: // copy like
		newOpc = HwtFpga::HWTFPGA_MUX;
		break;
	default:
		llvm_unreachable(
				"All cases should be covered in this switch in generic_opcode_to_hwtfpga");
	}
	if (addPredicate) {
		Observer.changingInstr(MI);
		auto MIB = MachineInstrBuilder(*MI.getMF(), &MI);
		MIB.addImm(1);
		Observer.changedInstr(MI);
	} else if (newOpc == HwtFpga::HWTFPGA_IMPLICIT_DEF) {
		Observer.changingInstr(MI);
		auto dst = MI.getOperand(0).getReg();
		auto Ty = MRI.getType(dst);
		assert(Ty.isValid());
		assert(Ty.isScalar());
		auto MIB = MachineInstrBuilder(*MI.getMF(), &MI);
		MIB.addImm(Ty.getSizeInBits()); // add dstWidth
		Observer.changedInstr(MI);
	}
	replaceOpcodeWith(MI, newOpc);
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

void HwtFpgaCombinerHelper::rewriteConstMergeValues(llvm::MachineInstr &MI,
		const llvm::APInt &replacement) {
	auto Dst = MI.getOperand(0).getReg();
	auto CurTy = MRI.getType(Dst);
	if (CurTy.isValid()) {
		assert(CurTy.getSizeInBits() == replacement.getBitWidth());
	} else {
		MRI.setType(Dst, LLT::scalar(replacement.getBitWidth()));
	}
	replaceInstWithConstant(MI, replacement);
}

bool HwtFpgaCombinerHelper::matchTrivialInstrDuplication(
		llvm::MachineInstr &MI) {
	assert(!MI.hasUnmodeledSideEffects());
	auto NextInst = MI.getNextNode();
	if (!NextInst || NextInst->getOpcode() != MI.getOpcode()
			|| NextInst->getNumOperands() != MI.getNumOperands()) {
		return false;
	}
	for (auto def : MI.defs()) {
		auto r = def.getReg();
		if (NextInst->findRegisterUseOperand(r))
			return false; // next instr uses result of this
	}
	// check def operands
	bool allDefsDead = true;
	for (auto I0 : { &MI, NextInst }) {
		auto I1 = I0 == &MI ? NextInst : &MI;
		for (auto def : I0->defs()) {
			if (!MRI.hasOneDef(def.getReg())) {
				return false; // result register used on multiple places, the check for liveness would be required
			} else if (def.isDead()) {
				continue; // this is subject to DCE, skip this
			} else if (I1->readsRegister(def.getReg())) {
				return false; // The instruction is using the result of other
			}
			allDefsDead = false;
		}
	}
	if (allDefsDead)
		return false; // this is subject to DCE, skip this

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

void HwtFpgaCombinerHelper::rewriteTrivialInstrDuplication(
		llvm::MachineInstr &MI) {
	assert(MI.getNumDefs() == 1);
	auto *OtherMI = MI.getNextNode();
	for (const auto [def0, def1] : zip(MI.defs(), OtherMI->defs())) {
		if (def0.getReg() != def1.getReg())
			replaceRegWith(MRI, def0.getReg(), def1.getReg());
	}

	MI.eraseFromParent();
}

bool HwtFpgaCombinerHelper::matchAndOrSequenceReduce(llvm::MachineInstr &MI,
		bool &removeRightOp) {
	auto opc = MI.getOpcode();
	switch (opc) {
	case TargetOpcode::G_AND:
	case TargetOpcode::G_OR:
	case HwtFpga::HWTFPGA_AND:
	case HwtFpga::HWTFPGA_OR:
		break;
	default:
		llvm_unreachable("Implemented only for and/or");
	}
	if (!MRI.hasOneDef(MI.getOperand(0).getReg()) || !MI.getOperand(1).isReg()
			|| !MI.getOperand(2).isReg())
		return false;
	Register r0 = MI.getOperand(1).getReg(), r1 = MI.getOperand(2).getReg();
	auto *prev = MI.getPrevNode();
	if (!prev)
		return false;
	if (prev->getOpcode() != opc)
		return false;
	auto prevRes = prev->getOperand(0).getReg();
	for (auto &op : { prev->getOperand(1), prev->getOperand(2) }) {
		if (op.isReg()) {
			auto prevOpR = op.getReg();
			if (prevRes == r0) {
				if (r1 == prevOpR) {
					removeRightOp = true;
					return true;
				}
			} else if (prevRes == r1) {
				if (r0 == prevOpR) {
					removeRightOp = false;
					return true;
				}
			}
		}
	}

	return false;
}

void HwtFpgaCombinerHelper::rewriteAndOrSequenceReduce(llvm::MachineInstr &MI,
		bool removeRightOp) {
	Register replacement;
	if (removeRightOp) {
		replacement = MI.getOperand(1 + 0).getReg();
	} else {
		replacement = MI.getOperand(1 + 1).getReg();
	}
	if (!MRI.hasOneDef(replacement)) {
		// create a copy because register can be used after it is potentially modified somewhere else
		auto _replacement = MRI.cloneVirtualRegister(replacement);
		Builder.setInstr(MI);
		Builder.buildInstr(HwtFpga::HWTFPGA_MUX, { _replacement },
				{ replacement });
		replacement = _replacement;
	}
	replaceRegWith(MRI, MI.getOperand(0).getReg(), replacement);
	MI.eraseFromParent();
}

MachineOperand* HwtFpgaCombinerHelper::getNextUseOfRegInBlock(MachineInstr &MI,
		Register &DstRegNo) {
	if (!MRI.hasOneUse(DstRegNo)) {
		for (MachineInstr *NextInstr = MI.getNextNode(); NextInstr != nullptr;
				NextInstr = NextInstr->getNextNode()) {
			// :note: redefs checked later in checkAnyOperandRedefined
			auto UseOpIndx = NextInstr->findRegisterUseOperandIdx(DstRegNo,
					false);
			if (UseOpIndx > 0) {
				return &NextInstr->getOperand(UseOpIndx);
			}
		}
	}
	return nullptr;
}

bool HwtFpgaCombinerHelper::checkAnyOperandRedefined(MachineInstr &MI,
		MachineInstr &MIEnd) {
	const MachineBasicBlock &MBB = *MI.getParent();
	if (&MBB != MIEnd.getParent()) {
		return true; // search in a different block not implemented
	}
	auto it = MachineBasicBlock::instr_iterator(&MI);
	++it;
	for (; it != MBB.instr_end(); ++it) {
		if (&*it == &MIEnd) {
			// found the otherMI as a successor
			return false;
		}
		for (auto &O : MI.operands()) {
			if (O.isReg()) {
				if (it->definesRegister(O.getReg())) {
					// the operand register was redefined and we do not have value for operand which we want to inline
					return true;
				}
			}
		}
	}
	// end was not found at all it means that end is actually a predecessor
	return true;
}

MachineOperand* HwtFpgaCombinerHelper::getNextUseOfRegAfterInstructionExceptMI(
		Register DstRegNo, MachineInstr &MI) {
	if (!MRI.hasOneDef(DstRegNo)
			&& MI.findRegisterUseOperandIdx(DstRegNo) > 0) {
		// Dst must have just this def or previous def must not be operand
		return nullptr;
	}

	MachineOperand *otherUse = nullptr;
	if (!MRI.hasOneUse(DstRegNo)) {
		otherUse = getNextUseOfRegInBlock(MI, DstRegNo);
		if (!otherUse) {
			// nothing to merge
			return nullptr;
		}
	} else {
		if (MRI.use_empty(DstRegNo))
			return nullptr;
		otherUse = &*MRI.use_begin(DstRegNo);
	}

	MachineInstr *otherMI = otherUse->getParent();
	if (otherMI == &MI) {
		return nullptr; // can not inline operands of self to self
	}
	return otherUse;
}

}
