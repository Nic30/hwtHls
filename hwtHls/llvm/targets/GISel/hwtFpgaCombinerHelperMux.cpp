#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/GlobalISel/GISelKnownBits.h>
#include <llvm/ADT/STLExtras.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/machineInstrUtils.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelectorUtils.h>
#include <hwtHls/llvm/bitMath.h>

namespace llvm {

bool HwtFpgaCombinerHelper::hasSomeConstConditions(MachineInstr &MI) {
	// dst, a, (cond, b)*
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	unsigned condCnt = (MI.getNumExplicitOperands() - 1) / 2;
	for (unsigned i = 0; i < condCnt; ++i) {
		auto &c = MI.getOperand(2 + i * 2);
		if (c.isCImm()) {
			return true;
		}
	}
	return false;
}

bool HwtFpgaCombinerHelper::rewriteConstCondMux(MachineInstr &MI) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	auto opIt = MI.operands_begin();
	Builder.setInstrAndDebugLoc(MI);
	auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
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

bool checkAnyOperandRedefined(MachineInstr &MI, MachineInstr &MIEnd) {
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

MachineOperand *getNextUseOfRegInBlock(MachineRegisterInfo &MRI, MachineInstr &MI,
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
bool HwtFpgaCombinerHelper::matchNestedMux(MachineInstr &MI,
		SmallVector<bool> &requiresAndWithParentCond) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	requiresAndWithParentCond.clear();
	// check if is used only by a HWTFPGA_MUX and can merge operands into user
	auto DstRegNo = MI.getOperand(0).getReg();
	if (!MRI.hasOneDef(DstRegNo) && MI.findRegisterUseOperandIdx(DstRegNo) > 0) {
		// Dst must have just this def or previous def must not be operand
		return false;
	}

	MachineOperand *otherUse = nullptr;
	if (!MRI.hasOneUse(DstRegNo)) {
		otherUse = getNextUseOfRegInBlock(MRI, MI, DstRegNo);
		if (!otherUse) {
			// nothing to merge
			return false;
		}
	} else {
		otherUse = &*MRI.use_begin(DstRegNo);
	}
	MachineInstr *otherMI = otherUse->getParent();
	if (otherMI == &MI) {
		return false; // can not inline operands of self to self
	}

	if (otherMI->getOpcode() != HwtFpga::HWTFPGA_MUX) {
		return false;
	}

	size_t otherUseOpIndex = otherMI->getOperandNo(otherUse);
	bool otherUseIsValueOp = otherUseOpIndex % 2 == 1;
	if (!otherUseIsValueOp)
		return false;
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
			bool mustAndWithParentCond = !CanMergeOperands.has_value()
					|| !CanMergeOperands.value();
			requiresAndWithParentCond.push_back(mustAndWithParentCond);
			NestedValO += 2; // skip condition and jump directly to new value
		}
		return true;
	}
}

bool HwtFpgaCombinerHelper::rewriteNestedMuxToMux(MachineInstr &MI,
		const SmallVector<bool> &requiresAndWithParentCond) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	auto DstRegNo = MI.getOperand(0).getReg();
	assert((MRI.hasOneDef(DstRegNo) || MI.findRegisterUseOperandIdx(DstRegNo) < 0)
			&& "Dst must have just this def or previous def must not be operand");
	MachineOperand *parentUse = nullptr;
	if (MRI.hasOneUse(DstRegNo)) {
		parentUse = &*MRI.use_begin(DstRegNo);
		assert(parentUse->getReg() == DstRegNo);
	} else {
		MachineInstr* NextInstr = getNextUseOfRegInBlock(MRI, MI, DstRegNo)->getParent();
		assert(NextInstr && "Should be already checked in matchNestedMux");
		assert(NextInstr->getOpcode() == HwtFpga::HWTFPGA_MUX);
		auto UseOpIndx = NextInstr->findRegisterUseOperandIdx(DstRegNo, false);
		assert(UseOpIndx > 0);
		parentUse = &NextInstr->getOperand(UseOpIndx);
		assert(parentUse->getReg() == DstRegNo);

	}
	// :note: parentMI is a MUX which is using MI
	//    we are now tying to remove MI by inline of MI into parentMI
	//    MI is removed if dst has no other use or MI.dst is parentMi.dst
	MachineInstr *parentMI = parentUse->getParent();
	assert(parentMI->getOpcode() == HwtFpga::HWTFPGA_MUX);

	Builder.setInstrAndDebugLoc(*parentMI);
	auto MIB0 = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
	auto &newParentMI = *MIB0.getInstr();
	Observer.changingInstr(newParentMI);
	auto newParentDst = parentMI->getOperand(0).getReg();

	for (size_t ParentOpI = 0; ParentOpI < parentMI->getNumOperands();
			++ParentOpI) {
		auto &Op = parentMI->getOperand(ParentOpI);
		if (&Op == parentUse) {
			// copy ops from nested MUX (replace this value operand with operands from MI)
			bool first = true;
			bool nestedOpIsCond = false;
			unsigned condI = 0;
			for (auto NesOp : MI.operands()) {
				if (first) {
					first = false;
					continue; // skip dst
				}

				if (nestedOpIsCond && requiresAndWithParentCond.size()
						&& requiresAndWithParentCond[condI]) {
					assert(ParentOpI + 1 < parentMI->getNumOperands());
					MachineOperand &parentCondOp = parentMI->getOperand(ParentOpI + 1);

					if (NesOp.getReg() == DstRegNo) {
						MIB0.addUse(newParentDst);
					} else if (NesOp.getReg() == parentCondOp.getReg()) {
						MIB0.add(NesOp);
					} else {
						Builder.setInstrAndDebugLoc(newParentMI);
						auto MIB1 = Builder.buildInstr(TargetOpcode::G_AND);
						auto &newCondAndMI = *MIB1.getInstr();
						Observer.changingInstr(newCondAndMI);
						Register newCondAndReg = MRI.createVirtualRegister(
								&HwtFpga::anyregclsRegClass);
						MIB1.addDef(newCondAndReg);
						for (auto &v : { NesOp.getReg(), parentCondOp.getReg() }) {
							MIB1.addUse(v);
						}
						Observer.changedInstr(newCondAndMI);

						Builder.setInstrAndDebugLoc(newParentMI);
						MIB0.addUse(newCondAndReg);
					}
				} else {
					if (NesOp.isReg() && NesOp.getReg() == DstRegNo) {
						MIB0.addUse(newParentDst);
					} else {
						MIB0.add(NesOp);
					}
				}
				if (nestedOpIsCond)
					condI++;
				nestedOpIsCond = !nestedOpIsCond;
			}
		} else {
			// copy rest of non modified operands from parent MUX
			MIB0.add(Op);
		}
	}

	Observer.changedInstr(newParentMI);

	if (DstRegNo == newParentDst || MRI.use_empty(DstRegNo)
			|| all_of(MRI.use_instructions(DstRegNo),
					// MI is only user of its dst
					[&MI](const MachineInstr &_MI) {
						return &_MI == &MI;
					})
		)
		MI.eraseFromParent();
	parentMI->eraseFromParent();

	return true;
}

bool HwtFpgaCombinerHelper::hasAll1AndAll0Values(MachineInstr &MI,
		hwtHls::CImmOrRegWithNegFlag &matchinfo) {
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
							== HwtFpga::HWTFPGA_NOT) {
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
							== HwtFpga::HWTFPGA_NOT) {
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

bool HwtFpgaCombinerHelper::rewriteConstValMux(MachineInstr &MI,
		const hwtHls::CImmOrRegWithNegFlag &matchinfo) {
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
				if (vdef->getParent()->getOpcode() == HwtFpga::HWTFPGA_NOT) {
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
		}
		replaceSingleDefInstWithReg(MI, replacement);
	}

	return true;
}

bool HwtFpgaCombinerHelper::matchMuxMask(llvm::MachineInstr &MI,
		BuildFnTy &rewriteFn) {
	if (MI.getNumOperands() == 1 + 3) { // dst, ifTrue, cond, ifFalse
		const auto &LHS = MI.getOperand(1);
		const auto &C = MI.getOperand(2);
		const auto &RHS = MI.getOperand(3);
		if (!C.isReg()) {
			return false;
		}
		unsigned width;
		unsigned Opc;
		const MachineOperand *xOp;
		if (RHS.isCImm() && RHS.getCImm()->isZeroValue()) {
			// (MUX  x, c, 0) -> (G_AND x, (SEXT c))
			width = RHS.getCImm()->getBitWidth();
			Opc = TargetOpcode::G_AND;
			xOp = &LHS;
		} else if (LHS.isCImm() && LHS.getCImm()->isAllOnesValue()) {
			// (MUX -1, c, x) -> (G_OR x, (SEXT c))
			width = LHS.getCImm()->getBitWidth();
			Opc = TargetOpcode::G_OR;
			xOp = &RHS;
		} else {
			return false;
		}
		//  (SEXT is avoided if x.width == 1)
		auto x = hwtHls::CImmOrReg(*xOp);
		auto CReg = C.getReg();
		Register Dst = MI.getOperand(0).getReg();
		if (width == 1) {
			rewriteFn = [=](MachineIRBuilder &builder) {
				auto MIB = builder.buildInstr(Opc);
				MIB.addDef(Dst);
				x.addAsUse(MIB);
				MIB.addUse(CReg);
			};
			return true;
		} else {
			//rewriteFn = [=](MachineIRBuilder & builder) {
			//	auto MIB = builder.buildInstr(Opc);
			//				MIB.addDef(Dst);
			//				x.addAsUse(MIB);
			//				MIB.addUse(CReg);
			//			};
		}

	}
	return false;
}

bool HwtFpgaCombinerHelper::matchMuxDuplicitCaseReduce(llvm::MachineInstr &MI,
		llvm::SmallVector<unsigned> &duplicitCaseConditions) {
	duplicitCaseConditions.clear();
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	unsigned opCnt = MI.getNumOperands();
	unsigned condCnt = (opCnt - 1) / 2;
	llvm::SmallSet<Register, 32> seenConditions;
	for (unsigned i = 0; i < condCnt; ++i) {
		auto CIndex = 2 + i * 2;	// +1 to skip dst, +1 to skip value operand
		auto &c = MI.getOperand(CIndex);
		if (c.isReg()) {
			if (seenConditions.contains(c.getReg())) {
				duplicitCaseConditions.push_back(CIndex);
			} else {
				seenConditions.insert(c.getReg());
			}
		}
	}
	return !duplicitCaseConditions.empty();
}

bool HwtFpgaCombinerHelper::rewriteMuxRmCases(llvm::MachineInstr &MI,
		const llvm::SmallVector<unsigned> &caseConditionsToRm) {
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	Observer.changingInstr(MI);
	for (unsigned CondI : llvm::reverse(caseConditionsToRm)) {
		MI.removeOperand(CondI); // c
		MI.removeOperand(CondI - 1); // v
	}
	Observer.changedInstr(MI);
	return true;
}

bool HwtFpgaCombinerHelper::matchMuxRedundantCase(llvm::MachineInstr &MI,
		llvm::SmallVector<unsigned> &caseConditionsToRm) {
	caseConditionsToRm.clear();
	assert(MI.getOpcode() == HwtFpga::HWTFPGA_MUX);
	assert(MI.getNumImplicitOperands() == 0);
	unsigned opCnt = MI.getNumOperands();
	unsigned condCnt = (opCnt - 1) / 2;
	for (int i = condCnt - 1; i >= 0; --i) {
		auto CIndex = 2 + i * 2; // +1 to skip dst, +1 to skip value operand
		auto &v0 = MI.getOperand(1 + i * 2);
		unsigned v1I = 3 + i * 2;
		assert(
				v1I < opCnt
						&& "there must be else value because this is not just copy implemented using mux because there is a condition");
		auto &v1 = MI.getOperand(v1I);
		if (hwtHls::MachineOperand_isIdenticalTo_ignoringFlags(v0, v1)) {
			caseConditionsToRm.push_back(CIndex);
		} else {
			break;
		}
	}
	return !caseConditionsToRm.empty();
}
}
