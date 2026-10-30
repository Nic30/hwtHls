#include <cassert>
#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>

#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/IR/Function.h>
#include <hwtHls/llvm/targets/Analysis/liveVariableForEdge.h>

#define DEBUG_TYPE "vreg-liveins"

using namespace llvm;

namespace hwtHls {

char HwtHlsVRegLiveins::ID = 0;

HwtHlsVRegLiveins::HwtHlsVRegLiveins() :
		MachineFunctionPass(ID), MF(nullptr), TRI(nullptr) {
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
void HwtHlsVRegLiveins::_collectIgnoredRegisters(
	const llvm::MachineFunction &MF) {
	for (auto &MBB : MF) {
		for (auto &MI : MBB) {
			if (isInstructionWhichIsKeeptOutOfLiveness(MI)) {
				for (auto &MO : MI.defs()) {
					ignoredRegisters.insert(MO.getReg());
				}
			}
		}
	}
}
bool HwtHlsVRegLiveins::runOnMachineFunction(llvm::MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;

	this->MF = &MF;
	auto &MRI = MF.getRegInfo();
	this->TRI = MF.getSubtarget().getRegisterInfo();

    // :attention: the same object is used for analysis of all MFs
	// assert(_liveins.empty());
	_liveins.clear();
	ignoredRegisters.clear();
	_collectIgnoredRegisters(MF);

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
			if (req_if_predecessor_is) {
				if (!defines[req_if_predecessor_is].contains(liveinReg))
					AddLiveinRecursively(defines, *req_if_predecessor_is, liveinReg,
						_liveins);
			} else {
				// requires from all predecessors
				for (auto *predMBB : block.predecessors()) {
					if (!defines[predMBB].count(liveinReg)) {
						AddLiveinRecursively(defines, *predMBB, liveinReg,
								_liveins);
					}
				}
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
	assert(MBB.getParent() != nullptr && "Assert block in in a parent function");
	for (auto *Suc : MBB.successors()) {
		auto liveins = _liveins.find(Suc);
		assert(Suc->getParent() == MBB.getParent());
		assert(liveins != _liveins.end() && "Assert that the block was known to his analysis");
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
	if (any_of(CurMBB.instrs(), [RegToAdd, this](const llvm::MachineInstr &MI) {
		return MI.definesRegister(RegToAdd, TRI);
	})
		)
		return;
}

void HwtHlsVRegLiveins::removeBlock(MachineBasicBlock * MBB) {
	_liveins.erase(MBB);
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

	// 2. The condition operand in branch may require "killed" flag if the register is not liveout of the block.
	if (CondOp.isKill() && !isLiveout(MBB, CondOp.getReg())) {
		CondOp.setIsKill(true);
	}
}

void HwtHlsVRegLiveins::UpdateKillAndDeadFlags(llvm::MachineBasicBlock &MBB) {
	std::set<llvm::Register> pendingUses;
	collectLiveouts(MBB, pendingUses);
	// iterate instructions from end, operands in latest use first direction
	// * if the use is not followed by any use it should have kill
	// * if the def is not followed by any use it should have dead
	// * uses are initialized from liveouts,
	//   if register is defined, uses after are forgotten
	
	// To cover cases like
	//  %0 = COPY %0
	//  ->
	//  %0 = COPY kill %0
	llvm::SmallSet<llvm::Register, 4> seenUsesWithDef;
	for (MachineInstr &MI : reverse(MBB)) {
		for (MachineOperand &MO : reverse(MI.operands())) {
			if (!MO.isReg()) {
				continue;
			}

			auto Reg = MO.getReg();
			if (MO.isUse()) {
				const bool MIDefinesReg = MI.definesRegister(Reg, TRI);
				if (!pendingUses.contains(Reg) ||
					(MIDefinesReg && seenUsesWithDef.insert(Reg).second)) {
					// the latest remaining use
					MO.setIsKill(true);
					pendingUses.insert(Reg);
				} else {
					MO.setIsKill(false);
				}
				continue;
			}

			assert(MO.isDef());
			if (pendingUses.contains(Reg)) {
				// used later-> not dead
				MO.setIsDead(false);
				if (!MI.readsRegister(Reg, TRI)) {
					// Example:
					//   %0 = COPY ...
					// > %0 = COPY %0
					// %0 must be kept alive for first COPY.
					pendingUses.erase(Reg);
				}
			} else {
				// no later uses
				MO.setIsDead(true);
			}
		}
	}
}

void HwtHlsVRegLiveins::UpdateKillAndDeadFlags(llvm::MachineFunction &MF) {
	for (auto &MBB : MF) {
		UpdateKillAndDeadFlags(MBB);
	}
}

void HwtHlsVRegLiveins::UpdateLiveinsBeforeNewPredecessorAdd(llvm::MachineBasicBlock &MBB, llvm::MachineBasicBlock &NewPredecMBB) {
	std::set<llvm::Register> liveouts;
	collectLiveouts(NewPredecMBB, liveouts);
	auto & liveins = liveinsMutable(MBB);
	liveins.insert(liveouts.begin(), liveouts.end());
}

void HwtHlsVRegLiveins::recompute() {
	runOnMachineFunction(*MF);
}
void HwtHlsVRegLiveins::verifyAnalysis() const {
	HwtHlsVRegLiveins other;
	other.runOnMachineFunction(*MF);
	// for (auto &BB : *MF) {
	//	assert(other._liveins.contains(&BB));
	//	assert(_liveins.contains(&BB));
	// }
	// assert(_liveins == other._liveins);

	const TargetRegisterInfo *TRI = MF->getSubtarget().getRegisterInfo();

	bool valid = true;
	for (auto &BB : *MF) {
		auto CurIt = _liveins.find(&BB);
		auto RecomputedIt = other._liveins.find(&BB);

		if (CurIt == _liveins.end()) {
			valid = false;
			errs() << "  Missing liveins for ";
			BB.printAsOperand(errs());
			errs() << "\n";
			continue;
		}

		const auto &Cur = CurIt->second;
		const auto &Recomputed = RecomputedIt->second;
		if (BB.isEntryBlock() || BB.pred_empty()) {
			for (auto Reg : Cur) {
				valid = false;
				BB.printAsOperand(errs());
				errs() << ": liveins on block without predecessors: "
					   << printVRegOrUnit(Reg, TRI) << "\n";
			}
		}
		//  else {
		// 	for (auto Reg : ignoredRegisters) {
		// 		if (!Cur.contains(Reg)) {
		// 			valid = false;
		// 			BB.printAsOperand(errs());
		// 			errs() << ": liveins missing ignored register: "
		// 				   << printVRegOrUnit(Reg, TRI) << "\n";
		// 		}
		// 	}
		// }
		for (auto Reg : Cur) {
			if (!Recomputed.contains(Reg)) {
				valid = false;
				BB.printAsOperand(errs());
				errs() << ": liveins contain extra: "
					<< printVRegOrUnit(Reg, TRI) << "\n";
			}
		}

		for (auto Reg : Recomputed) {
			if (!Cur.contains(Reg)) {
				valid = false;
				BB.printAsOperand(errs());
				errs() << ": missing livein: " << printVRegOrUnit(Reg, TRI)
					   << "\n";
			}
		}
	}

	for (const auto &[BB, Liveins] : _liveins) {
		if (!other._liveins.contains(BB)) {
			valid = false;
			errs() << "  liveins refer to MBB not in MF: ";
			BB->printAsOperand(errs());
			errs() << "\n";
		}
	}

	if (!valid) {
		assert(false && "HwtHlsVRegLiveins cached liveins do not match "
						"recomputed liveins");
	}
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

