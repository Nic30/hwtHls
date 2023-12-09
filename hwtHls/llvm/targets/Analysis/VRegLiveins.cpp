#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>

#include <llvm/ADT/SetVector.h>
#include <hwtHls/llvm/targets/Analysis/liveVariableForEdge.h>

#define DEBUG_TYPE "vreg-liveins"

using namespace llvm;

namespace hwtHls {

char HwtHlsVRegLiveins::ID = 0;

HwtHlsVRegLiveins::HwtHlsVRegLiveins() :
		MachineFunctionPass(ID), MF(nullptr) {
	initializeHwtHlsVRegLiveinsPass(*PassRegistry::getPassRegistry());
}

void HwtHlsVRegLiveins::getAnalysisUsage(AnalysisUsage &AU) const {
	AU.setPreservesAll();
	MachineFunctionPass::getAnalysisUsage(AU);
}

void AddLiveinRecursively(
		std::map<MachineBasicBlock*, SetVector<Register>> &defines,
		MachineBasicBlock &MBB, Register v,
		std::map<MachineBasicBlock*, SetVector<Register>> &liveins) {
	auto &_live = liveins[&MBB];

	if (_live.count(v)) {
		return;
	}

	_live.insert(v);
	for (auto *pred : MBB.predecessors()) {
		if (!defines[pred].count(v)) {
			AddLiveinRecursively(defines, *pred, v, liveins);
		}
	}
}

bool HwtHlsVRegLiveins::runOnMachineFunction(llvm::MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;
	this->MF = &MF;
	auto &MRI = MF.getRegInfo();

	assert(_liveins.empty());

	std::map<MachineBasicBlock*, SetVector<Register>> defines;
	std::map<MachineBasicBlock*,
			SetVector<std::pair<Register, MachineBasicBlock*>>> liveinsTmp;
	// initialization
	for (MachineBasicBlock &block : MF) {
		liveinsTmp[&block] =
				SetVector<std::pair<Register, MachineBasicBlock*>>();
		collectDirectLiveinsAndDefines(MRI, block,
				[](llvm::MachineRegisterInfo &MRI,
						const llvm::MachineInstr &MI) {
					return false;
				}, liveinsTmp[&block], defines[&block]);
	}
	for (auto &MBB : MF) {
		_liveins[&MBB] = llvm::SetVector<llvm::Register>();
	}
	// transitive enclosure of requires relation
	for (MachineBasicBlock &block : MF) {
		auto &BlockLiveins = _liveins[&block];
		for (auto _requirement : liveinsTmp[&block]) {
			Register liveinReg;
			MachineBasicBlock *req_if_predecessor_is;
			std::tie(liveinReg, req_if_predecessor_is) = _requirement;
			BlockLiveins.insert(liveinReg);
			if (req_if_predecessor_is == nullptr) {
				// requires from all predecessors
				for (auto *predMBB : block.predecessors()) {
					if (!defines[predMBB].count(liveinReg)) {
						AddLiveinRecursively(defines, *predMBB, liveinReg,
								_liveins);
					}
				}
			} else {
				AddLiveinRecursively(defines, *req_if_predecessor_is, liveinReg,
						_liveins);
			}
		}
	}
	UpdateKillAndDeadFlags(MF);
	return false;
}

llvm::SetVector<llvm::Register>& HwtHlsVRegLiveins::liveinsMutable(
		const llvm::MachineBasicBlock &MBB) {
	MachineBasicBlock *_MBB = const_cast<MachineBasicBlock*>(&MBB);
	return _liveins.find(_MBB)->second;
}

const llvm::SetVector<llvm::Register>& HwtHlsVRegLiveins::liveins(
		const llvm::MachineBasicBlock &MBB) const {
	return const_cast<HwtHlsVRegLiveins*>(this)->liveinsMutable(MBB);
}

bool HwtHlsVRegLiveins::isLivein(const llvm::MachineBasicBlock &MBB,
		llvm::Register r) const {
	return liveins(MBB).contains(r);
}

bool HwtHlsVRegLiveins::isAnyPredecessorLiveout(
		const llvm::MachineBasicBlock &MBB, llvm::Register r) const {
	SmallSet<const llvm::MachineBasicBlock*, 16> seen;
	for (auto *Pred : MBB.predecessors()) {
		for (auto *Suc : Pred->successors()) {
			if (!seen.contains(Suc)) {
				if (isLivein(*Suc, r))
					return true;
				seen.insert(Suc);
			}
		}
	}
	return false;
}

bool HwtHlsVRegLiveins::isLiveout(const llvm::MachineBasicBlock &MBB,
		Register r) const {
	for (auto *Suc : MBB.successors()) {
		auto liveins = _liveins.find(Suc);
		assert(liveins != _liveins.end());
		if (liveins->second.count(r)) {
			return true;
		}
	}
	return false;
}

void HwtHlsVRegLiveins::collectLiveouts(const llvm::MachineBasicBlock &MBB,
		std::set<llvm::Register> &liveouts) const {
	for (auto *Suc : MBB.successors()) {
		auto &SucLiveins = _liveins.find(Suc)->second;
		liveouts.insert(SucLiveins.begin(), SucLiveins.end());
	}
}

void HwtHlsVRegLiveins::_addToLivenessUntillBlock(
		llvm::MachineBasicBlock &CurMBB, llvm::MachineBasicBlock &TargetMBB,
		llvm::Register RegToAdd) {
	if (&CurMBB == &TargetMBB)
		return;
	auto &liveins = liveinsMutable(CurMBB);
	if (liveins.contains(RegToAdd))
		return;
	liveins.insert(RegToAdd);
	for (auto &Pred : CurMBB.predecessors()) {
		_addToLivenessUntillBlock(*Pred, TargetMBB, RegToAdd);
	}
}

void HwtHlsVRegLiveins::addToLivenessRecursively(
		llvm::MachineBasicBlock &CurMBB, llvm::Register RegToAdd) {
	llvm::MachineRegisterInfo &MRI = CurMBB.getParent()->getRegInfo();
	auto *def = MRI.getOneDef(RegToAdd);
	if (def) {
		_addToLivenessUntillBlock(CurMBB, *def->getParent()->getParent(),
				RegToAdd);
	} else {
		_addToLivenessRecursively(CurMBB, RegToAdd);
	}
}

void HwtHlsVRegLiveins::_addToLivenessRecursively(
		llvm::MachineBasicBlock &CurMBB, llvm::Register RegToAdd) {
	auto &liveins = liveinsMutable(CurMBB);
	if (liveins.contains(RegToAdd))
		return;
	if (any_of(CurMBB.instrs(), [RegToAdd](const llvm::MachineInstr &MI) {
		return MI.definesRegister(RegToAdd);
	})
		)
		return;
}

void HwtHlsVRegLiveins::UpdateAfterInsertBranch(llvm::MachineBasicBlock &MBB) {
	// 1. If the definition of branch cond register is outside of the block and it is not in live ins of this block,
	//    it has to be added to liveins (and "killed flag has to be added")
	auto Term = MBB.terminators().begin();
	if (Term == MBB.terminators().end() || !Term->isConditionalBranch())
		return; // no update because there is no condition in terminating branch

	auto &CondOp = Term->getOperand(0);
	assert(CondOp.isReg() && "Branch condition should be always register");
	addToLivenessRecursively(MBB, CondOp.getReg());

	// 2. The condition may operand in branch may require "killed" flag if the register is not liveout of the block.
	if (CondOp.isKill() && !isLiveout(MBB, CondOp.getReg())) {
		CondOp.setIsKill(true);
	}
}

void HwtHlsVRegLiveins::UpdateKillAndDeadFlags(llvm::MachineBasicBlock &MBB) {
	std::set<llvm::Register> liveouts;
	collectLiveouts(MBB, liveouts);
	for (MachineInstr &MI : reverse(MBB)) {
		for (MachineOperand &MO : MI.operands()) {
			if (MO.isReg()) {
				auto Reg = MO.getReg();
				if (liveouts.find(Reg) == liveouts.end()) {
					if (MO.isUse()) {
						MO.setIsKill(true);
						liveouts.insert(Reg);
					} else {
						assert(MO.isDef());
						MO.setIsDead(true);
					}
				} else {
					if (!MO.isImplicit()) {
						if (MO.isUse()) {
							MO.setIsKill(false);
						} else {
							MO.setIsDead(false);
						}
					}
				}
			}
		}
	}
}

void HwtHlsVRegLiveins::UpdateKillAndDeadFlags(llvm::MachineFunction &MF) {
	for (auto &MBB : MF) {
		UpdateKillAndDeadFlags(MBB);
	}
}

void HwtHlsVRegLiveins::recompute() {
	_liveins.clear();
	runOnMachineFunction(*MF);
}

void HwtHlsVRegLiveins::print(llvm::raw_ostream &O, const Module *M) const {
	O << getPassName() << ":\n";
	if (MF) {
		for (auto &MBB : *MF) {
			O << "liveins: [";
			bool first = true;
			for (auto LI : liveins(MBB)) {
				if (first) {
					first = false;
				} else {
					O << ", ";
				}
				O << LI.virtRegIndex();
			}
			O << "]\n";
			O << MBB << "\n";
		}
	} else {
		O << "  <no MF>\n";
	}
}
}

using namespace hwtHls;
INITIALIZE_PASS(HwtHlsVRegLiveins, DEBUG_TYPE,
		"MachineBasicBlock VRegLiveins Pass", false, true)

