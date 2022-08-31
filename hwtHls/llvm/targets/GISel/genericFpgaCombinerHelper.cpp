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
		if (hwtHls::GenericFpgaInstructionSelector::machineOperandTryGetConst(
				Context, MRI, MO)) {
			return true;
		}
	}
	return false;
}

bool GenFpgaCombinerHelper::rewriteG_CONSTANTasUseAsCImm(
		llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	auto MIB = Builder.buildInstr(MI.getOpcode());
	auto &newMI = *MIB.getInstr();
	Observer.changingInstr(newMI);
	hwtHls::GenericFpgaInstructionSelector::selectInstrArgs(MI, MIB,
			MI.getOperand(0).isDef());
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

bool GenFpgaCombinerHelper::matchAllOnesConstantOp(
		const llvm::MachineOperand &MOP) {
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
bool GenFpgaCombinerHelper::matchOperandIsAllOnes(llvm::MachineInstr &MI,
		unsigned OpIdx) {
	return matchAllOnesConstantOp(MI.getOperand(OpIdx))
			&& (MI.getOperand(OpIdx).isCImm()
					|| canReplaceReg(MI.getOperand(0).getReg(),
							MI.getOperand(OpIdx).getReg(), MRI));
}
bool GenFpgaCombinerHelper::rewriteXorToNot(llvm::MachineInstr &MI) {
	Builder.setInstrAndDebugLoc(MI);
	Builder.buildInstr(GenericFpga::GENFPGA_NOT, { MI.getOperand(0).getReg() },
			{ MI.getOperand(1).getReg() }, MI.getFlags());
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

bool GenFpgaCombinerHelper::matchIsExtractOnMergeValues(
		llvm::MachineInstr &MI) {
	auto _src = MI.getOperand(1);
	if (_src.isReg()) {
		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			return src->getParent()->getOpcode()
					== GenericFpga::GENFPGA_MERGE_VALUES;
		}
	}
	return false;
}

inline bool collectConcatMembersAsItIs(llvm::MachineOperand &MIOp,
		std::vector<GenFpgaCombinerHelper::ConcatMember> &members,
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
		members.push_back(GenFpgaCombinerHelper::ConcatMember { MIOp,
				offsetOfIRes, widthOfIRes, bitsToTake });
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
bool GenFpgaCombinerHelper::collectConcatMembers(llvm::MachineOperand &MIOp,
		std::vector<ConcatMember> &members, uint64_t mainOffset,
		uint64_t mainWidth, uint64_t &currentOffset, uint64_t offsetOfIRes,
		uint64_t widthOfIRes) {
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
	case GenericFpga::GENFPGA_EXTRACT: {
		// $dst $src $offset $dstWidth
		uint64_t subSliceOffset = MI.getOperand(2).getImm();
		uint64_t subSliceWidth = MI.getOperand(3).getImm();
		subSliceOffset += offsetOfIRes;
		if (widthOfIRes > subSliceWidth) {
			errs() << MI << " widthOfIRes:" << widthOfIRes << "\n";
			llvm_unreachable(
					"GENFPGA_EXTRACT provides value of less bits than expected");
		}
		//subSliceWidth = std::min(std::min(subSliceWidth - offsetOfIRes,
		//		mainEnd - currentOffset), );
		if (auto *src = MRI.getOneDef(MI.getOperand(1).getReg())) {
			// look trough the source operand of this extract instruction
			bool didReduce = collectConcatMembers(*src, members, mainOffset,
					mainWidth, currentOffset, subSliceOffset, subSliceWidth);
			assert(members.size());
			const auto &lastAdded = members.back();
			didReduce |= &lastAdded.op != src;
			return didReduce;
		}

		break;
	}
	}
	return collectConcatMembersAsItIs(MIOp, members, mainOffset, mainWidth,
			currentOffset, offsetOfIRes, widthOfIRes);
}

void addSrcOperand(MachineInstrBuilder &MIB,
		GenFpgaCombinerHelper::ConcatMember &src) {
	if (src.op.isReg() && src.op.isDef())
		MIB.addUse(src.op.getReg());
	else {
		MIB.add(src.op);
	}
}
bool GenFpgaCombinerHelper::rewriteExtractOnMergeValues(
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
			MRI.replaceRegWith(MI.getOperand(0).getReg(), src.op.getReg()); // [fixme] the src.op can be imm or cost

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
				auto memberMIB = Builder.buildInstr(
						GenericFpga::GENFPGA_EXTRACT);
				// $dst $src $offset $dstWidth
				Register memberReg = MRI.createVirtualRegister(
						&GenericFpga::AnyRegClsRegClass);
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

//bool GenFpgaCombinerHelper::matchMuxWithRedundantCases(llvm::MachineInstr &MI,
//		llvm::SmallVector<unsigned> &uselessConditions) {
//	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
//	unsigned opCnt = MI.getNumOperands();
//	unsigned condCnt = (opCnt - 1) / 2;
//	for (unsigned i = 0; i < condCnt; ++i) {
//		auto &v0 = MI.getOperand(1 + i * 2);
//		auto &c = MI.getOperand(2 + i * 2);
//		MachineOperand *v1 = nullptr;
//		unsigned v1I = 3 + i * 2;
//		if (v1I < opCnt)
//			v1 = &MI.getOperand(v1I);
//		bool muxOfSameVal = false;
//		if (v1 && c.isReg()) {
//			if ((v0.isReg() && v1->isReg() && v0.getReg() == v1->getReg())
//					|| (v0.isCImm() && v1->isCImm()
//							&& v0.getCImm() == v1->getCImm())) {
//				// if left and right val is the same and this is one-hot encoded mux
//				muxOfSameVal = true;
//			}
//		} else if (i == 0 && v0.isReg()
//				&& v0.getReg() == MI.getOperand(0).getReg()) {
//			muxOfSameVal = true; // conditional write of self to self
//		}
//
//	}
//}
//
//bool GenFpgaCombinerHelper::rewriteMuxWithRedundantCases(llvm::MachineInstr &MI,
//		const llvm::SmallVector<unsigned> &uselessConditions) {
//	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
//
//}

bool GenFpgaCombinerHelper::hashSomeConstConditions(llvm::MachineInstr &MI) {
	// dst, a, (cond, b)*
	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
	unsigned condCnt = (MI.getNumOperands() - 1) / 2;
	for (unsigned i = 0; i < condCnt; ++i) {
		auto &c = MI.getOperand(2 + i * 2);
		if (c.isCImm()) {
			return true;
		}
	}
	return false;
}

bool GenFpgaCombinerHelper::rewriteConstCondMux(llvm::MachineInstr &MI) {
	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
	auto opIt = MI.operands_begin();
	Builder.setInstrAndDebugLoc(MI);
	auto MIB = Builder.buildInstr(GenericFpga::GENFPGA_MUX);
	auto &newMI = *MIB.getInstr();
	Observer.changingInstr(newMI);
	MIB.add(*opIt); // dst
	++opIt;
	for (;;) {
		auto v0 = opIt++;
		if (opIt == MI.operands_end()) {
			// ending  value
			MIB.add(*v0);
		} else {
			auto c = opIt++;
			if (c->isCImm()) {
				if (c->getCImm()->getValue().getBoolValue()) {
					// if 1 the successor operands are never used
					MIB.add(*v0);
					break;
				} else {
					// if 0 the v0 is never used
				}
			} else {
				MIB.add(*v0);
				MIB.add(*c);
			}
		}
		if (opIt == MI.operands_end()) {
			break;
		}
	}
	Observer.changedInstr(newMI);
	MI.eraseFromParent();
	return true;
}

bool checkAnyOperandRedefined(llvm::MachineInstr &MI,
		llvm::MachineInstr &MIEnd) {
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

/**
 * rules for merging MUX instructions:
 * * if conditions are proven to be exclusive the order of pairs condition-value does not matter
 *   The equality can be checked in using KnownBits :see: `CombinerHelper::matchICmpToTrueFalseKnownBits`
 *   .. code-block:: cpp
 *     	auto KnownLHS = KB->getKnownBits(MI.getOperand(2).getReg());
 * 	  	auto KnownRHS = KB->getKnownBits(MI.getOperand(3).getReg());
 *      Optional<bool> KnownVal = KnownBits::ne(KnownLHS, KnownRHS);
 *
 * * y = MUX v0
 *   x = MUX y c0 v1
 *   ->
 *   x = MUX v0 c0 v1 // this is a trivial case where we just copy V0 no mater in which operand of mux x the y is used
 *
 * * y = MUX v1 c1 v2
 *   x = MUX v0 c0 y
 *   ->
 *   x = MUX v0 c0 v1 c1 v2  // merging on "tail" is just copy of arguments from first to second
 *
 * * y = MUX v1 c1 v2
 *   x = MUX y c0 v0
 *   ->
 *   x = MUX v1 (c1 & c0) v2 y c0 v0 // or C0 can be reversed to move y at the end
 *   x = MUX v0 !c0 v1 c1 v2
 *
 * * y = MUX v3 c2 v4
 *   x = MUX v0 c0 y c1 v2
 *   ->
 *   x = MUX v0 c0 v3 (c2 & c1) v4 c1 v2
 *   x = MUX v0 c0 v2 ~c1 v3 c2 v4 // or C1 can be reversed to move y at the end
 *
 */
bool GenFpgaCombinerHelper::matchNestedMux(llvm::MachineInstr &MI,
		llvm::SmallVector<bool> &requiresAndWithParentCond) {
	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
	requiresAndWithParentCond.clear();
	// check if is used only by a GENFPGA_MUX and can merge operands into user
	auto DstRegNo = MI.getOperand(0).getReg();
	if (!MRI.hasOneUse(DstRegNo)) {
		// if there are multiple users merging of this register is not beneficial
		return false;
	}

	MachineOperand *otherUse = &*MRI.use_begin(DstRegNo);
	MachineInstr *otherMI = otherUse->getParent();
	if (otherMI == &MI) {
		return false; // can not inline operands of self to self
	}

	if (otherMI->getOpcode() != GenericFpga::GENFPGA_MUX) {
		return false;
	}

	// check that the operand register are not redefined between this and other
	if (checkAnyOperandRedefined(MI, *otherMI)) {
		return false;
	}

	// check how we can nest this MI to otherMI
	// if the merged-in MUX:
	if (MI.getNumOperands() == 2) {
		// has a single operand -> move it to otherMI mux
		return true;
	} else if (MachineInstr::mop_iterator(otherUse) + 1
			== otherMI->operands_end()) {
		// is last operand -> move NestedI operands to this mux
		for (unsigned condI = 1 + 1; condI < MI.getNumOperands(); condI += 2) {
			requiresAndWithParentCond.push_back(false);
		}
		return true;
	} else {
		// is in format similar to:
		// %MI      = MUX v3 c2 v4
		// %OtherMI = MUX v0 c0 %MI c1 v2
		//  check if conditions from NestedI are always satisfied if c1
		auto c1 = MachineInstr::mop_iterator(otherUse) + 1;
		if (!c1->isReg()) {
			return false;// wait with the extraction for removal of constant conditions
		}
		KnownBits KnownC1 = KB->getKnownBits(c1->getReg());
		for (auto NestedValO = MI.operands_begin() + 1;
				NestedValO != MI.operands_end();) {

			auto NestedCondO = NestedValO + 1;
			if (NestedCondO == MI.operands_end()) {
				break;
			}
			if (!NestedCondO->isReg()) {
				// wait with the extraction for removal of constant conditions
				return false;
			}
			KnownBits KnownNestedC = KB->getKnownBits(NestedCondO->getReg());
			// c1 is always 1 if NestedCond is 1 (NestedCond implies c1)
			Optional<bool> CanMergeOperands = KnownBits::uge(KnownC1,
					KnownNestedC);
			bool mustAndWithParentCond = !CanMergeOperands.hasValue()
					|| !CanMergeOperands.getValue();
			requiresAndWithParentCond.push_back(mustAndWithParentCond);
			NestedValO += 2; // skip condition and jump directly to new value
		}
		return true;
	}
}

bool GenFpgaCombinerHelper::rewriteNestedMuxToMux(llvm::MachineInstr &MI,
		const llvm::SmallVector<bool> &requiresAndWithParentCond) {
	assert(MI.getOpcode() == GenericFpga::GENFPGA_MUX);
	MachineOperand *parentUse = &*MRI.use_begin(MI.getOperand(0).getReg());
	MachineInstr *parentMI = parentUse->getParent();

	Builder.setInstrAndDebugLoc(*parentMI);
	auto MIB0 = Builder.buildInstr(GenericFpga::GENFPGA_MUX);
	auto &newMI = *MIB0.getInstr();
	Observer.changingInstr(newMI);

	for (auto &Op : parentMI->operands()) {
		if (&Op == parentUse) {
			// copy ops from nested MUX
			bool first = true;
			bool isCond = false;
			unsigned condI = 0;
			for (auto NesOp : MI.operands()) {
				if (first) {
					first = false;
					continue;
				}
				if (isCond && requiresAndWithParentCond.size()
						&& requiresAndWithParentCond[condI]) {
					llvm::MachineOperand & parentCondOp = parentMI->getOperand(parentMI->getOperandNo(&Op) + 1);
					Builder.setInstrAndDebugLoc(newMI);
					auto MIB1 = Builder.buildInstr(TargetOpcode::G_AND);
					auto &newCondAndMI = *MIB1.getInstr();
					Observer.changingInstr(newCondAndMI);
					Register newCondAndReg = MRI.createVirtualRegister(
							&GenericFpga::AnyRegClsRegClass);
					MIB1.addDef(newCondAndReg);
					for (auto & v: {NesOp.getReg(), parentCondOp.getReg()}) {
						MIB1.addUse(v);
					}
					Observer.changedInstr(newCondAndMI);

					Builder.setInstrAndDebugLoc(newMI);
					MIB0.addUse(newCondAndReg);

				} else {
					MIB0.add(NesOp);
				}
				isCond = !isCond;
			}
		} else {
			// copy rest of non modified operands from parent MUX
			MIB0.add(Op);
		}
	}

	Observer.changedInstr(newMI);
	MI.eraseFromParent();
	parentMI->eraseFromParent();
	return true;
}

bool GenFpgaCombinerHelper::hasAll1AndAll0Values(llvm::MachineInstr &MI,
		CImmOrRegWithNegFlag &matchinfo) {
	matchinfo.CImm = nullptr;
	matchinfo.Negate = false;

	if (MI.getNumOperands() == 1 + 3) {
		auto &v0 = MI.getOperand(1);
		auto &c0 = MI.getOperand(2);
		auto &v1 = MI.getOperand(3);
		LLT Ty = MRI.getType(MI.getOperand(0).getReg());
		bool is1b = Ty.isScalar() && Ty.getSizeInBits() == 1;

		if (v0.isReg() && v1.isReg()) {
			if (v0.getReg() == v1.getReg()) {
				// c ? v:v -> v
				matchinfo.Reg = v0.getReg();
				return true;

			} else if (is1b) {
				if (MachineOperand *v0def = MRI.getOneDef(v0.getReg())) {
					if (v0def->getParent()->getOpcode()
							== GenericFpga::GENFPGA_NOT) {
						auto &v0_n = v0def->getParent()->getOperand(1);
						if (v0_n.isReg() && v0_n.getReg() == v1.getReg()) {
							// c ? ~v:v -> ~c
							if (c0.isReg()) {
								matchinfo.Reg = c0.getReg();
							} else {
								matchinfo.CImm = c0.getCImm();
							}
							matchinfo.Negate = true;
							return true;
						}
					}

				} else if (MachineOperand *v1def = MRI.getOneDef(v1.getReg())) {
					if (v1def->getParent()->getOpcode()
							== GenericFpga::GENFPGA_NOT) {
						auto &v1_n = v0def->getParent()->getOperand(1);
						if (v1_n.isReg() && v1_n.getReg() == v1.getReg()) {
							// c ? v:~v -> c
							if (c0.isReg()) {
								matchinfo.Reg = c0.getReg();
							} else {
								matchinfo.CImm = c0.getCImm();
							}
							return true;
						}
					}
				}
			}

		} else if (v0.isCImm() && v1.isCImm()) {
			auto vc0 = v0.getCImm();
			auto vc1 = v1.getCImm();
			if (vc0->getValue() == vc1->getValue()) {
				matchinfo.CImm = vc0;
				return true;

			} else if (is1b) {
				if (vc0->isZero() && vc1->isAllOnesValue()) {
					// c ? 0:1 -> ~c
					if (c0.isReg()) {
						matchinfo.Reg = c0.getReg();
					} else {
						matchinfo.CImm = c0.getCImm();
					}
					matchinfo.Negate = true;
					return true;

				} else if (vc1->isZero() && vc0->isAllOnesValue()) {
					// c ? 1:0 -> c
					if (c0.isReg()) {
						matchinfo.Reg = c0.getReg();
					} else {
						matchinfo.CImm = c0.getCImm();
					}
					return true;
				}
			}
		}
	}

	return false;
}

bool GenFpgaCombinerHelper::rewriteConstValMux(llvm::MachineInstr &MI,
		const CImmOrRegWithNegFlag &matchinfo) {
	if (matchinfo.CImm) {
		if (matchinfo.Negate) {
			replaceInstWithConstant(MI, ~matchinfo.CImm->getValue());
		} else {
			replaceInstWithConstant(MI, matchinfo.CImm->getValue());
		}
	} else {
		Register replacement = matchinfo.Reg;
		if (matchinfo.Negate) {
			if (MachineOperand *vdef = MRI.getOneDef(matchinfo.Reg)) {
				if (vdef->getParent()->getOpcode()
						== GenericFpga::GENFPGA_NOT) {
					auto &v_n = vdef->getParent()->getOperand(1);
					if (v_n.isReg()) {
						replacement = v_n.getReg();
					} else {
						replaceInstWithConstant(MI, v_n.getCImm()->getValue());

						MI.eraseFromParent();
						return true;
					}
				}
			}
			//replaceSingleDefInstWithReg(MI, );
		}
		replaceSingleDefInstWithReg(MI, replacement);
	}

	MI.eraseFromParent();
	return true;
}

}
