#include "genericFpgaCombinerHelper.h"
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include "../genericFpgaInstrInfo.h"
#include "genericFpgaInstructionSelectorUtils.h"

namespace llvm {

bool GenFpgaCombinerHelper::hashOnlyConstUses(llvm::MachineInstr &MI) {
	for (auto &op : MI.uses()) {
		if (op.isReg())
			return false;
	}
	return true;
}

bool GenFpgaCombinerHelper::rewriteConstExtract(llvm::MachineInstr &MI) {
	auto _v = MI.getOperand(1).getCImm();
	const APInt &v = _v->getValue();
	auto bitPosition = MI.getOperand(2).getImm();
	auto numBits = MI.getOperand(3).getImm();
	replaceInstWithConstant(MI, v.extractBits(numBits, bitPosition));
	return true;
}

bool GenFpgaCombinerHelper::hasG_CONSTANTasUse(llvm::MachineInstr &MI) {
	auto &Context = MI.getMF()->getFunction().getContext();
	for (auto &MO : MI.uses()) {
		if (hwtHls::GenericFpgaInstructionSelector::machineOperandTryGetConst(Context, MRI, MO)) {
			return true;
		}
	}
	return false;
}

bool GenFpgaCombinerHelper::rewriteG_CONSTANTasUseAsCImm(llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	auto MIB = Builder.buildInstr(MI.getOpcode());
	auto &newMI = *MIB.getInstr();
	Observer.changingInstr(newMI);
	hwtHls::GenericFpgaInstructionSelector::selectInstrArgs(MI, MIB, MI.getOperand(0).isDef());
	Observer.changedInstr(newMI);
	MI.eraseFromParent();
	return true;
}

bool GenFpgaCombinerHelper::rewriteConstMergeValues(llvm::MachineInstr &MI) {
	// $dst $src{N}, $width{N} (lowest bits first)
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

bool GenFpgaCombinerHelper::matchAllOnesConstantOp(const llvm::MachineOperand &MOP) {
	if (MOP.isCImm()) {
		return MOP.getCImm()->getValue().isAllOnes();
	}
	if (!MOP.isReg()) {
		return false;
	}
	auto *MI = MRI.getVRegDef(MOP.getReg());
	auto MaybeCst = isConstantOrConstantSplatVector(*MI, MRI);
	return MaybeCst.hasValue() && MaybeCst->isAllOnes();
}
bool GenFpgaCombinerHelper::matchOperandIsAllOnes(llvm::MachineInstr &MI, unsigned OpIdx) {
	return matchAllOnesConstantOp(MI.getOperand(OpIdx))
			&& (MI.getOperand(OpIdx).isCImm()
					|| canReplaceReg(MI.getOperand(0).getReg(), MI.getOperand(OpIdx).getReg(), MRI));
}
bool GenFpgaCombinerHelper::rewriteXorToNot(llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	Builder.buildInstr(GenericFpga::GENFPGA_NOT, { MI.getOperand(0).getReg() }, { MI.getOperand(1).getReg() },
			MI.getFlags());
	MI.eraseFromParent();
	return true;
}

bool GenFpgaCombinerHelper::rewriteConstBinOp(llvm::MachineInstr &MI,
		std::function<APInt(const APInt&, const APInt&)> fn) {
	auto _v = MI.getOperand(1).getCImm();
	const APInt &a = _v->getValue();
	const APInt &b = MI.getOperand(2).getCImm()->getValue();
	replaceInstWithConstant(MI, fn(a, b));
	return true;
}

bool GenFpgaCombinerHelper::matchIsExtractOnMergeValues(llvm::MachineInstr &MI) {
	auto _src = MI.getOperand(1);
	if (_src.isReg()) {
		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			return src->getParent()->getOpcode() == GenericFpga::GENFPGA_MERGE_VALUES;
		}
	}
	return false;
}

inline bool collectConcatMembersAsItIs(llvm::MachineOperand &MIOp,
		std::vector<GenFpgaCombinerHelper::ConcatMember> &members, uint64_t mainOffset, uint64_t mainWidth,
		uint64_t &currentOffset, uint64_t offsetOfIRes, uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	// take slice from this instruction as it is
	uint64_t bitsToTake = std::min(widthOfIRes, mainEnd - currentOffset);
	currentOffset += widthOfIRes;
	if (currentOffset < mainOffset) {
		// skip prefix
		return true;
	} else {
		members.push_back(GenFpgaCombinerHelper::ConcatMember { MIOp, offsetOfIRes, widthOfIRes, bitsToTake });
		return false;
	}
}
/*
 * Recursively collect members of concatenations, looks trought GENFPGA_EXTRACT and GENFPGA_MERGE_VALUES instructions
 *
 * :param MIOp: an operand from where to collect concat embers
 * :param members: output vector of records containing the operand and the information about which bits are selected
 * :param mainOffset: offsets (number of bits) where selected value from whole value
 * :param mainWidth: number of bits to select in total
 * :param currentOffset: a number of bits already collected
 * :param offsetOfIRes: offsets (number of bits) where selected value from this operand starts
 * :param widthOfIRes: a number of bits to select from this operand
 * */
bool GenFpgaCombinerHelper::collectConcatMembers(llvm::MachineOperand &MIOp, std::vector<ConcatMember> &members,
		uint64_t mainOffset, uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes, uint64_t widthOfIRes) {
	uint64_t mainEnd = mainOffset + mainWidth;
	MachineInstr &MI = *MIOp.getParent();
	switch (MI.getOpcode()) {
	case GenericFpga::GENFPGA_MERGE_VALUES: {
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
					didReduce |= collectConcatMembers(*src, members, mainOffset, mainWidth, currentOffset,
							thisMemberOffset, width);
				} else {
					// must take as it is
					collectConcatMembersAsItIs(op, members, mainOffset, mainWidth, currentOffset, thisMemberOffset,
							width);
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
	case GenericFpga::GENFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		uint64_t subSliceOffset = MI.getOperand(2).getImm();
		uint64_t subSliceResWidth = MI.getOperand(3).getImm();
		subSliceOffset += offsetOfIRes;
		if (widthOfIRes > subSliceResWidth) {
			errs() << MI << " widthOfIRes:" << widthOfIRes << "\n";
			llvm_unreachable("GENFPGA_EXTRACT provides value of less bits than expected");
		}

		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			// look trough the source operand of this extract instruction
			bool mayContainOtherSlicesAndConcats = false;
			switch (src->getParent()->getOpcode()) {
			case GenericFpga::GENFPGA_MERGE_VALUES:
			case GenericFpga::GENFPGA_EXTRACT:
				mayContainOtherSlicesAndConcats = true;
				break;
			}
			if (mayContainOtherSlicesAndConcats) {
				bool didReduce = collectConcatMembers(*src, members, mainOffset, mainWidth, currentOffset,
						subSliceOffset, subSliceResWidth); // [fixme] subSliceResWidth is not correct it should be the width of src but it is unknown at this point
				assert(members.size());
				const auto &lastAdded = members.back();
				didReduce |= &lastAdded.op != src;
				return didReduce;
			}
		}

		break;
	}
	}
	return collectConcatMembersAsItIs(MIOp, members, mainOffset, mainWidth, currentOffset, offsetOfIRes, widthOfIRes);
}

void addSrcOperand(MachineInstrBuilder &MIB, GenFpgaCombinerHelper::ConcatMember &src) {
	if (src.op.isReg() && src.op.isDef())
		MIB.addUse(src.op.getReg());
	else {
		MIB.add(src.op);
	}
}
bool GenFpgaCombinerHelper::rewriteExtractOnMergeValues(llvm::MachineInstr &MI) {
	// MI.operands() == $dst $src $offset $dstWidth
	std::vector<ConcatMember> concatMembers;
	//uint64_t mainOffset = MI.getOperand(2).getImm();
	uint64_t mainWidth = MI.getOperand(3).getImm();
	uint64_t currentOffset = 0;
	bool didReduce = collectConcatMembers(MI.getOperand(0), concatMembers, 0, mainWidth, currentOffset, 0, mainWidth);
	if (!didReduce)
		return false;
	assert(concatMembers.size() && "There must be something which EXTRACT selects");
	if (concatMembers.size() == 1) {
		auto &src = concatMembers.back();
		// we may be able to use item directly of we may build an EXTRACT
		if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
			if (src.op.isReg()) {
				MRI.replaceRegWith(MI.getOperand(0).getReg(), src.op.getReg());
			} else if (src.op.isCImm()) {
				Builder.setInstrAndDebugLoc(MI);
				Register srcReg = MRI.createVirtualRegister(&GenericFpga::AnyRegClsRegClass);
				Builder.buildConstant(srcReg, *src.op.getCImm());
				MRI.replaceRegWith(MI.getOperand(0).getReg(), srcReg);
			} else {
				llvm_unreachable("GenFpgaCombinerHelper::rewriteExtractOnMergeValues unexpected type of src operand");
			}
		} else {
			Builder.setInstrAndDebugLoc(MI);
			auto MIB = Builder.buildInstr(GenericFpga::GENFPGA_EXTRACT);
			// $dst $src $offset $dstWidth
			MIB.addDef(MI.getOperand(0).getReg(), MI.getFlags());
			addSrcOperand(MIB, src);
			MIB.addImm(src.offsetOfUse);
			MIB.addImm(src.widthOfUse);
		}
	} else {
		// we must build GENFPGA_MERGE_VALUE for members
		Builder.setInstrAndDebugLoc(MI);
		auto currentInsertionPoint = Builder.getInsertPt();
		auto MIB = Builder.buildInstr(GenericFpga::GENFPGA_MERGE_VALUES);
		MIB.addDef(MI.getOperand(0).getReg(), MI.getFlags());

		for (auto &src : concatMembers) {
			if (src.offsetOfUse == 0 && src.width == src.widthOfUse) {
				// use member directly
				addSrcOperand(MIB, src);
			} else {
				// slice the member using GENFPGA_EXTRACT
				Builder.setInstrAndDebugLoc(MI);
				Builder.setInsertPt(*MI.getParent(), --currentInsertionPoint);
				auto memberMIB = Builder.buildInstr(GenericFpga::GENFPGA_EXTRACT);
				// $dst $src $offset $dstWidth
				Register memberReg = MRI.createVirtualRegister(&GenericFpga::AnyRegClsRegClass);
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

GenFpgaCombinerHelper::CImmOrReg::CImmOrReg(const MachineOperand &MOP) {
	if (MOP.isReg()) {
		c = nullptr;
		reg = MOP.getReg();
	} else if (MOP.isCImm()) {
		c = MOP.getCImm();
		reg = 0;
	} else {
		llvm_unreachable("need reg or CImm for GENFPGA_EXTRACT");
	}
}

GenFpgaCombinerHelper::CImmOrReg::CImmOrReg(const ConstantInt *c) {
	this->c = c;
	reg = 0;
}

void GenFpgaCombinerHelper::CImmOrReg::addAsUse(MachineInstrBuilder &MIB) const {
	if (c)
		MIB.addCImm(c);
	else {
		MIB.addUse(reg);
	}
}

Register buildMsbGet(MachineIRBuilder &builder, GISelChangeObserver &Observer, GenFpgaCombinerHelper::CImmOrReg x,
		unsigned bitWidth, Optional<Register> dst) {
	auto MIB = builder.buildInstr(GenericFpga::GENFPGA_EXTRACT);
	auto &newMI = *MIB.getInstr();

	Observer.changingInstr(newMI);
	Register msbReg;
	if (dst.hasValue()) {
		msbReg = dst.getValue();
	} else {
		msbReg = builder.getMRI()->createVirtualRegister(&GenericFpga::AnyRegClsRegClass);
	}
	MIB.addDef(msbReg);
	x.addAsUse(MIB); // src
	MIB.addImm(bitWidth - 1); // offset
	MIB.addImm(1); // dst width
	Observer.changedInstr(newMI);

	return msbReg;
}

bool GenFpgaCombinerHelper::matchCmpToMsbCheck(llvm::MachineInstr &MI, BuildFnTy &rewriteFn) {
	auto Pred = static_cast<CmpInst::Predicate>(MI.getOperand(1).getPredicate());
	auto LHS = MI.getOperand(2);
	auto RHS = MI.getOperand(3);

	if ((Pred == CmpInst::Predicate::ICMP_SGE && RHS.isCImm() && RHS.getCImm()->getValue().isZero())
			|| (Pred == CmpInst::Predicate::ICMP_SGT && matchAllOnesConstantOp(RHS))) {
		// (SGE x,  0) -> NOT x.msb
		// (SGT x, -1) -> NOT x.msb
		unsigned bitWidth = RHS.getCImm()->getType()->getIntegerBitWidth();
		Register Dst = MI.getOperand(0).getReg();
		CImmOrReg _LHS(LHS);
		rewriteFn = [bitWidth, Dst, _LHS, this](MachineIRBuilder &builder) {
			// msbReg = x.MSB
			Register msbReg = buildMsbGet(builder, Observer, _LHS, bitWidth, None);
			// res = not msbReg
			builder.buildInstr(GenericFpga::GENFPGA_NOT, { Dst }, { msbReg });
		};
		return true;
	} else if ((Pred == CmpInst::Predicate::ICMP_SLT && RHS.isCImm() && RHS.getCImm()->getValue().isZero())
			|| (Pred == CmpInst::Predicate::ICMP_SGT && matchAllOnesConstantOp(RHS))) {
		// (SLT x,  0) -> x.msb
		// (SGT x, -1) -> x.msb
		unsigned bitWidth = RHS.getCImm()->getType()->getIntegerBitWidth();
		Register Dst = MI.getOperand(0).getReg();
		CImmOrReg _LHS(LHS);
		rewriteFn = [bitWidth, Dst, _LHS, this](MachineIRBuilder &builder) {
			// res = msbReg = x.MSB
			buildMsbGet(builder, Observer, _LHS, bitWidth, Dst);
		};
		return true;
	}
	return false;
}

bool GenFpgaCombinerHelper::matchConstCmpConstAdd(llvm::MachineInstr &MI, BuildFnTy &rewriteFn) {
	assert(MI.getOpcode() == TargetOpcode::G_ICMP);
	auto Pred = static_cast<CmpInst::Predicate>(MI.getOperand(1).getPredicate());
	const auto LHS = MI.getOperand(2);
	const auto RHS = MI.getOperand(3);
	if (Pred == CmpInst::Predicate::ICMP_EQ || Pred == CmpInst::Predicate::ICMP_NE) { // [todo] rest of the predicates
		if (LHS.isReg() && RHS.isCImm()) {
			MachineOperand *_LHS = MRI.getOneDef(LHS.getReg());
			if (!_LHS)
				return false;
			auto lhsOpcode = _LHS->getParent()->getOpcode();
			if (lhsOpcode == TargetOpcode::G_ADD || lhsOpcode == TargetOpcode::G_SUB) {
				const auto LHS_LHS = _LHS->getParent()->getOperand(1);
				const auto LHS_RHS = _LHS->getParent()->getOperand(2);
				if (LHS_RHS.isCImm()) {
					// [fixme] assert that add/sub operands are not modified between  until icmp instr.
					APInt lhsVal = RHS.getCImm()->getValue(); // original value which was compared with
					auto lhsRhsVal = LHS_RHS.getCImm()->getValue(); // the const value used in add/sub
					switch (lhsOpcode) {
					case TargetOpcode::G_ADD:
						lhsVal -= lhsRhsVal;
						break;
					case TargetOpcode::G_SUB:
						lhsVal += lhsRhsVal;
					}

					CImmOrReg newLHS(LHS_LHS);
					ConstantInt *newRhs = ConstantInt::get(Builder.getMF().getFunction().getContext(), lhsVal);
					Register Dst = MI.getOperand(0).getReg();
					rewriteFn = [Dst, Pred, newLHS, newRhs, this](MachineIRBuilder &builder) {
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

bool GenFpgaCombinerHelper::isTrivialRemovableCopy(llvm::MachineInstr &MI) {
	/*
	 * Recognize
	 *  %0 = ...
     *  %1 = GENFPGA_MUX %0
     *  and replace it with just %0
	 * */
	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
	if (MI.getNumOperands() != 2)
		return false;
	auto & src = MI.getOperand(1);
	if (src.isReg() && MRI.hasOneUse(src.getReg())) {
		auto def = MRI.getOneDef(src.getReg());
		if (def && def->getParent()->getNextNode() == &MI) {
			return true;
		}
	}
	return false;
}

bool GenFpgaCombinerHelper::rewriteTrivialRemovableCopy(llvm::MachineInstr &MI){
	auto & dst = MI.getOperand(0);
	auto & src = MI.getOperand(1);
	auto def = MRI.getOneDef(src.getReg());
	def->setReg(dst.getReg());
	MI.eraseFromParent();
	return true;
}

}
