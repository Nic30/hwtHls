#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <llvm/IR/Constants.h>
#include <llvm/CodeGen/GlobalISel/MIPatternMatch.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaRegisterInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionBuilderUtils.h>
#include <hwtHls/llvm/targets/machineInstrUtils.h>

using namespace llvm;
using namespace llvm::MIPatternMatch;

namespace hwtHls {

MachineOperand* getRegisterNegationIfExits(MachineRegisterInfo &MRI,
		llvm::MachineBasicBlock &TargetMBB,
		llvm::MachineBasicBlock::iterator TargetIp, Register reg,
		bool &wasOriginallyKillOrDead) {
	wasOriginallyKillOrDead = false;
	if (auto *DefMO = MRI.getOneDef(reg)) {
		auto &I = *DefMO->getParent();
		bool Op1CanBeUsed = false;
		switch (I.getOpcode()) {
		case HwtFpga::HWTFPGA_NOT:
		case TargetOpcode::G_XOR: {
			auto &Op1 = I.getOperand(1);
			if (Op1.isReg()) {
				if (MRI.isSSA()
						|| (I.getParent() == &TargetMBB
								&& !RegisterIsDefinedWithinRange(Op1.isReg(),
										++I.getIterator(), TargetIp))) {
					Op1CanBeUsed = true;
				}
			}
		}
		}
		if (Op1CanBeUsed)
			switch (I.getOpcode()) {
			case TargetOpcode::G_XOR: {
				auto &Op1 = I.getOperand(1);
				auto &Op2 = I.getOperand(2);
				if (match_OperandIs1(MRI, Op2)) {
					wasOriginallyKillOrDead = Op1.isKill();
					Op1.setIsKill(false);
					return &Op1;
				}
				break;
			}
			case HwtFpga::HWTFPGA_NOT: {
				auto &Op1 = I.getOperand(1);
				wasOriginallyKillOrDead = Op1.isKill();
				Op1.setIsKill(false);
				return &Op1;
			}
			}
	}

	bool isSSA = MRI.isSSA();
	// search if it is defined by negation which dominates this use or there already is a negation
	// begin at TargetIp and continue up until block has a single predecessor, then iterate again
	// to check if the register is not redefined along the path
	llvm::MachineBasicBlock *_TargetMBB = &TargetMBB;
	llvm::MachineBasicBlock::iterator _TargetIp = TargetIp;
	llvm::SmallPtrSet<MachineBasicBlock*, 32> seenBlocks;
	while (!seenBlocks.contains(_TargetMBB)) {
		while (_TargetIp != _TargetMBB->begin()) {
			MachineInstr &prevInstr = *--_TargetIp;

			bool TargetRegIsDefinedByNegation = false;
			bool FoundExistingNegationOfTargetReg = false;
			switch (prevInstr.getOpcode()) {
			case HwtFpga::HWTFPGA_NOT: {
				auto &Op0 = prevInstr.getOperand(0);
				auto &Op1 = prevInstr.getOperand(1);
				FoundExistingNegationOfTargetReg = Op1.isReg()
						&& Op1.getReg() == reg;
				if (!isSSA && !FoundExistingNegationOfTargetReg)
					TargetRegIsDefinedByNegation = Op0.getReg() == reg;
				break;
			}
			case TargetOpcode::G_XOR: {
				auto &Op0 = prevInstr.getOperand(0);
				auto &Op1 = prevInstr.getOperand(1);
				auto &Op2 = prevInstr.getOperand(2);
				FoundExistingNegationOfTargetReg = Op1.isReg()
						&& Op1.getReg() == reg;
				if (!isSSA && !FoundExistingNegationOfTargetReg) {
					TargetRegIsDefinedByNegation = Op0.getReg() == reg
							&& match_OperandIs1(MRI, Op2);
				}
				break;
			}
			}
			if (FoundExistingNegationOfTargetReg) {
				auto &Op0 = prevInstr.getOperand(0);
				if (Register_isRedefinedInLinearBlockSequenceEndToBegin(
						Op0.getReg(), prevInstr.getIterator(), TargetMBB,
						TargetIp)) {
					return nullptr;
				}
				wasOriginallyKillOrDead = Op0.isDead();
				Op0.setIsDead(false);
				return &Op0;
			}
			if (TargetRegIsDefinedByNegation
					&& prevInstr.getOperand(1).isReg()) {
				auto &Op1 = prevInstr.getOperand(1);
				if (Register_isRedefinedInLinearBlockSequenceEndToBegin(
						Op1.getReg(), prevInstr.getIterator(), TargetMBB,
						TargetIp)) {
					return nullptr;
				}
				wasOriginallyKillOrDead = Op1.isKill();
				Op1.setIsKill(false);
				return &Op1;
			}
			if (prevInstr.definesRegister(reg))
				return nullptr;
		}
		if (_TargetMBB->pred_size() != 1) {
			return nullptr;
		} else {
			seenBlocks.insert(_TargetMBB);
			_TargetMBB = *_TargetMBB->pred_begin();
			_TargetIp = _TargetMBB->end();
		}
	}
	return nullptr;
}

MachineOperand& _negateRegister(MachineRegisterInfo &MRI,
		MachineIRBuilder &Builder, Register reg, bool isKill) {
	Register BR_n = MRI.cloneVirtualRegister(reg); //MRI.createVirtualRegister(&HwtFpga::anyregclsRegClass);//(Cond[0].getReg());
	//MRI.setRegClass(BR_n, &HwtFpga::anyregclsRegClass);
	MRI.setType(BR_n, LLT::scalar(1));
	MRI.setType(reg, LLT::scalar(1));

	auto NegOne = Builder.buildConstant(LLT::scalar(1), 1);
	MRI.setRegClass(NegOne.getInstr()->getOperand(0).getReg(),
			&HwtFpga::anyregclsRegClass);
	//MRI.invalidateLiveness();
	auto MIB = Builder.buildInstr(TargetOpcode::G_XOR, { BR_n },
			{ reg, NegOne });
	if (isKill || MRI.hasOneUse(reg)) {
		MIB.getInstr()->getOperand(1).setIsKill();
	}
	MIB.getInstr()->getOperand(2).setIsKill();

	return MIB.getInstr()->getOperand(0);
}

Register negateRegister(MachineRegisterInfo &MRI, MachineIRBuilder &Builder,
		Register reg, bool isKill) {
	bool wasKillOrDead;
	auto existingN = getRegisterNegationIfExits(MRI, Builder.getMBB(),
			Builder.getInsertPt(), reg, wasKillOrDead);
	if (existingN) {
		return existingN->getReg();
	}
	return _negateRegister(MRI, Builder, reg, isKill).getReg();
}

std::pair<llvm::MachineIRBuilder, Register> negateRegisterForInstr(
		MachineInstr &MI, Register reg, bool isKill) {
	MachineBasicBlock *MBB = MI.getParent();
	assert(MBB);
	MachineFunction &MF = *MBB->getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	MachineIRBuilder Builder(*MBB, MI);
	Register reg_n = hwtHls::negateRegister(MRI, Builder, reg, isKill);
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

void predicateInstructionUsingDefRegRename(llvm::MachineRegisterInfo &MRI,
		const HwtHlsVRegLiveins &VRegLiveins, llvm::MachineInstr &MI,
		bimap<llvm::Register, llvm::Register> &regReplaces) {
	if (MI.isReturn())
		return;
	if (MI.hasUnmodeledSideEffects()) {
		errs() << MI << "\n";
		llvm_unreachable("Unexpected instruction with side effects");
	}
	if (MRI.isSSA()) {
		// for SSA this is not required, because there can not be any use
		// if this def instruction was not executed
		// that implies that any use can not reach previous value in current register
		// and thus this instruction may always execute if it has no side effect
		return;
	}
	auto &MBB = *MI.getParent();
	// Create temporary registers for defines if the register is live out of this block
	for (auto &MO : MI.operands()) {
		if (!MO.isReg() || MO.isUndef())
			continue;

		auto MOReg = MO.getReg();
		auto curReplacement = regReplaces.find1(MOReg);
		if (MO.isDef()) {
			// check if we have to create a temporary register for this define
			// or if it used only locally
			if (VRegLiveins.isAnyPredecessorLiveout(MBB, MOReg)
					&& VRegLiveins.isLiveout(MBB, MOReg)) {
				// used also outside of this block, must generate new reg
				if (!curReplacement.has_value()) {
					// if it was not yet replaced we create a temporary register as a replacement for this
					curReplacement = MRI.cloneVirtualRegister(MOReg);
					regReplaces.insert(MOReg, curReplacement.value());
				}
			}
		}
		if (curReplacement.has_value()) {
			MO.ChangeToRegister(curReplacement.value(), /*isDef*/
			MO.isDef(), /*isImp*/MO.isImplicit(), /*isKill*/
			MO.isKill(), /*isDead*/MO.isDead(), /*isUndef*/
			MO.isUndef(), /*isDebug*/MO.isDebug());
		}
	}
}

void createSpeculationMergeMuxes(llvm::MachineBasicBlock &insertPointBlock,
		llvm::MachineBasicBlock::iterator insertPointIt,
		const bimap<llvm::Register, llvm::Register> &regsForSpeculation,
		const llvm::ArrayRef<llvm::MachineOperand> &Predicate,
		llvm::MachineRegisterInfo &MRI) {

	if (!regsForSpeculation.empty()) {
		// insert MUXes to merge regs which were generated for speculation into original register
		std::map<Register, llvm::MachineInstr*> existingMuxes;
		if (Predicate.size() != 2) {
			// [todo] for every reg check if it is defined by MUX and if this is a cache,
			// check if the conditions contain Predicate conditions
			// for (auto & P: Predicate) {
			// 	errs() << P << "\n";
			// }
			// for (auto const & [Reg, regSpeculation] : regsForSpeculation.items()) {
			// 	errs() << "reg:" << Reg.virtRegIndex() << ": " << regSpeculation.virtRegIndex() << "\n";
			// }
			llvm_unreachable("NotImplemented - predicate with multiple terms");

			//for (auto const & [Reg, regSpeculation] : regsForSpeculation.items()) {
			//	for (llvm::MachineInstr & I: llvm::reverse(insertPointBlock)) {
			//		// find def in this block
			//		if (I.definesRegister(Reg)) {
			//			if (I.getOpcode() == HwtFpga::HWTFPGA_MUX) {
			//				// if I is MUX it may be possible to just prepend operands,
			//				// but we need to check if it can be moved at the end
			//				bool canUse = false;
			//				for (llvm::MachineInstr & I2: llvm::reverse(insertPointBlock)) {
			//					if (&I2 == &I) {
			//						canUse = true;
			//						break;
			//					} else if (I.definesRegister(regSpeculation)) {
			//
			//					}
			//				}
			//			}
			//			break;
			//		}
			//	}
			//}
		}
		bool isNegated = Predicate[1].getImm();
		Register Cond = Predicate[0].getReg();

		// update kill/dead of Cond (potentially rm previous kill, add kill to last mux if used never after)
		bool condShouldBeKilled = false;
		for (MachineInstr &predInstr : llvm::reverse(
				llvm::make_range(insertPointBlock.begin(), insertPointIt))) {
			for (auto &MO : predInstr.operands()) {
				if (MO.isReg() && MO.getReg() == Cond) {
					if (MO.isUse()) {
						condShouldBeKilled = MO.isKill();
						if (condShouldBeKilled)
							MO.setIsKill(false);
					} else {
						assert(MO.isDef());
						condShouldBeKilled = MO.isDead();
						if (condShouldBeKilled)
							MO.setIsDead(false);
					}
					break;
				}
			}
		}
		MachineIRBuilder Builder(insertPointBlock, insertPointIt);
		MachineInstr *lastI = nullptr;
		for (auto const& [reg, regSpeculation] : regsForSpeculation.items()) {
			// if the reg was not defined by MUX or we can not move MUX behind the definition of conditions in Predicate,
			// the mux has to be created
			auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
			MIB.addDef(reg);
			if (isNegated) {
				MIB.addUse(reg);
				MIB.addUse(Cond);
				MIB.addUse(regSpeculation, RegState::Kill);
			} else {
				MIB.addUse(regSpeculation, RegState::Kill);
				MIB.addUse(Cond);
				MIB.addUse(reg);
			}
			// else we prepend value, condition pair to current MUX,
			// optionally moving it behind def of last condition in predicate
			lastI = MIB.getInstr();
		}
		if (condShouldBeKilled) {
			assert(lastI);
			lastI->getOperand(2).setIsKill(true); // Cond
		}
	}
}

void Condition_and(llvm::MachineIRBuilder &Builder,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op0,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op1AndDst) {
	return Condition_and_or(TargetOpcode::G_AND, Builder, Op0, Op1AndDst);
}

void Condition_or(llvm::MachineIRBuilder &Builder,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op0,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op1AndDst) {
	return Condition_and_or(TargetOpcode::G_OR, Builder, Op0, Op1AndDst);
}

void Condition_and_or(unsigned opcode_and_or, llvm::MachineIRBuilder &Builder,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op0,
		llvm::SmallVectorImpl<llvm::MachineOperand> &Op1AndDst) {
	auto &TII = Builder.getTII();
	auto &MRI = *Builder.getMRI();
	// [todo] implement for or/and, in VRegIfConverter::IfConvertTriangle check when and/or should be used between conditions
	// e.g. GE subsumes GT.
	if (opcode_and_or != TargetOpcode::G_AND
			|| !TII.SubsumesPredicate(Op0, Op1AndDst)) {

		assert(Op0.size() == 2);
		assert(Op1AndDst.size() == 2);

		auto Src0 = Op0[0].getReg();
		if (Op0[1].getImm()) {
			// if is negated
			Src0 = hwtHls::negateRegister(MRI, Builder, Src0, Op0[0].isKill());
		}
		auto Src1 = Op1AndDst[0].getReg();
		if (Op1AndDst[1].getImm()) {
			// if is negated
			Src1 = hwtHls::negateRegister(MRI, Builder, Src1,
					Op1AndDst[0].isKill());
		}
		for (auto R: {Src0, Src1}) {
			if (!MRI.getType(R).isValid())
				MRI.setType(R, LLT::scalar(1));
		}
		auto Dst = MRI.cloneVirtualRegister(Op0[0].getReg());

		auto MIB = Builder.buildInstr(opcode_and_or, { Dst, }, { Src0, Src1 });
		Op1AndDst[0] = MIB.getInstr()->getOperand(0);
		Op1AndDst[1].setImm(0); // not negated
	}
}

class MPHIPairs {
	MachineInstr &MI;
public:
	MPHIPairs(MachineInstr &_MI) :
			MI(_MI) {
	}

	struct iterator {
		MachineInstr &MI;
		size_t opIndex;
	public:
		using iterator_category = std::forward_iterator_tag;
		using difference_type = std::ptrdiff_t;
		using value_type = std::pair<MachineOperand*, MachineOperand*>; // value_type (v, mbb);
		//using pointer           = int*;  // or also value_type*
		//using reference         = int&;

		explicit iterator(MachineInstr &_MI, size_t _opIndex = 0) :
				MI(_MI), opIndex(1 + _opIndex * 2) {
		}
		iterator& operator++() {
			opIndex += 2;
			return *this;
		}
		iterator operator++(int) {
			iterator retval = *this;
			++(*this);
			return retval;
		}
		bool operator==(iterator other) const {
			assert(&MI == &other.MI);
			return opIndex == other.opIndex;
		}
		bool operator!=(iterator other) const {
			return !(*this == other);
		}
		value_type operator*() const {
			MachineOperand &Src = MI.getOperand(opIndex);
			MachineOperand &SrcMBB = MI.getOperand(opIndex + 1);
			return {&Src, &SrcMBB};
		}
	};
	iterator begin() {
		return iterator(MI, 0);
	}
	iterator end() {
		return iterator(MI, (MI.getNumOperands() - 1) / 2);
	}
};

struct PhiPruningItem {
	MachineInstr *PHI;
	MachineOperand *TopV;
	MachineOperand *CvtV;
	// Result of Select instruction to replace TopV, CvtV values in phi operands
	// If nullptr it means that the whole PHI can be removed and any replacement is not required,
	// because new Select uses dst reg of this PHI.
	MachineOperand *selResult;
	PhiPruningItem(MachineInstr *PHI, MachineOperand *TopV,
			MachineOperand *CvtV, MachineOperand *selResult) :
			PHI(PHI), TopV(TopV), CvtV(CvtV), selResult(selResult) {
	}
};

void PHIsToSelectAfterIfCvt(HwtHlsVRegLiveins &VRegLiveins,
		llvm::MachineBasicBlock &TopMBB,
		const llvm::SmallVectorImpl<llvm::MachineOperand> &Cond,
		llvm::MachineBasicBlock &CvtTMBB, llvm::MachineBasicBlock &NextMBB) {

	assert(&TopMBB != &CvtTMBB);
	if (NextMBB.pred_size() != 1) {
		assert(
				NextMBB.pred_size() > 1
						&& "In triangle there should be EBB and TBB, TBB should be removed from successors");
	}
	// create a mux EBB/TBB val with EBB.br.cond as cond at the end of just if converted block CvtBB(TBB)
	bool CondRegIsNegated = false;
	bool CondWasOriginallyUnused = false;
	std::optional<Register> CondReg;
	MachineFunction &MF = *TopMBB.getParent();
	MachineRegisterInfo &MRI = MF.getRegInfo();
	MachineOperand *lastUseOfCond = nullptr;

	SmallVector<PhiPruningItem> toPrune;
	MachineIRBuilder MIRB(TopMBB, TopMBB.terminators().begin());

	for (MachineInstr &PHI : NextMBB.phis()) {
		// check if value from TBB or
		MachineOperand *TopV = nullptr;
		MachineOperand *CvtV = nullptr;

		for (const auto& [V, PredMBB] : MPHIPairs(PHI)) {
			if (PredMBB->getMBB() == &TopMBB) {
				assert(TopV == 0);
				TopV = V;
			} else if (PredMBB->getMBB() == &CvtTMBB) {
				CvtV = V;
			}
		}
		assert(TopV != nullptr);
		assert(CvtV != nullptr);
		// if TopV and CvtV are same, we do not have o create select
		if (MachineOperand_isIdenticalTo_ignoringFlags(*TopV, *CvtV)) {
			toPrune.push_back(PhiPruningItem(&PHI, TopV, CvtV, TopV));
			continue;
		}

		auto &Dst = PHI.getOperand(0);
		if (!CondReg.has_value()) {
			assert(Cond[0].isReg());
			MachineOperand Br_cond = Cond[0];
			bool isNegated = Cond[1].getImm();

			if (isNegated) {
				MachineOperand *_Br_n = hwtHls::getRegisterNegationIfExits(MRI,
						TopMBB, TopMBB.terminators().begin(), Br_cond.getReg(),
						CondWasOriginallyUnused);
				if (_Br_n) {
					// use existing negation of register
					Br_cond = *_Br_n;
				} else {
					CondRegIsNegated = true;
				}
			}
			if (!isNegated || CondRegIsNegated) {
				// is using original Br_cond
				CondWasOriginallyUnused = MRI.use_empty(Br_cond.getReg())
						|| Br_cond.isKill();
			}
			CondReg = Br_cond.getReg();
		}

		auto Op0 = *CvtV;
		auto Op1 = *TopV;
		if (CondRegIsNegated) {
			std::swap(Op0, Op1);
		}
		MachineInstr *sel;
		if (PHI.getNumOperands() == 1 + 2 * 2) {
			sel = MIRB.buildSelect(Dst, CondReg.value(), Op0, Op1).getInstr();
			toPrune.push_back(PhiPruningItem(&PHI, TopV, CvtV, nullptr));
		} else {
			Register SelDst = MRI.cloneVirtualRegister(Dst.getReg());
			sel =
					MIRB.buildSelect(SelDst, CondReg.value(), Op0, Op1).getInstr();
			toPrune.push_back(
					PhiPruningItem(&PHI, TopV, CvtV, &sel->getOperand(0)));
		}
		// :note: potential liveins from TopV/CvtV are not pruned

		// instead of TopV, CvtV the result of select is now livein to NextMBB
		VRegLiveins.liveinsMutable(NextMBB).insert(
				sel->getOperand(0).getReg());
		lastUseOfCond = &sel->getOperand(1);
	}

	if (CondWasOriginallyUnused && lastUseOfCond) {
		lastUseOfCond->setIsKill();
	}

	for (const auto &item : toPrune) {
		if (item.selResult) {
			if (item.PHI->getNumOperands() > 1 + 2 * 2) {
				MachineIRBuilder MIRB(NextMBB, item.PHI);
				auto MIB = MIRB.buildInstr(item.PHI->getOpcode());
				bool skipNextMO = false;
				for (auto &MO : item.PHI->operands()) {
					if (skipNextMO) {
						assert(MO.isMBB());
						assert(MO.getMBB() == &TopMBB || MO.getMBB() == &CvtTMBB);
						skipNextMO = false;
						continue;
					}
					if (&MO == item.CvtV || &MO == item.TopV) {
						skipNextMO = true;
						continue;
					}
					MIB.add(MO);
				}
				MIB.addUse(item.selResult->getReg(), RegState::Kill);
			} else {
				MRI.replaceRegWith(item.PHI->getOperand(0).getReg(), item.selResult->getReg());
			}
		}
		item.PHI->eraseFromParent();
	}
}

}
