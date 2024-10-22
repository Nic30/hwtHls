//===----------------------------------------------------------------------===//
//
// Functionality similar to llvm::MachineLateInstrsCleanupPass
// but it supports also virtual registers and it does not require
// def register operands to be he same
// * it uses structural hashing of operands to discover same instructions
//   in MBB
// * it performs simple copy propagation
// * normalizes the representations of constants and constant operands
//   to constant operands only if possible
// * has disabled handling for frame register (because HwtFpga has not any)
// * it does not do Partial-Redundancy Elimination (PRE)
//===----------------------------------------------------------------------===//

#include <hwtHls/llvm/targets/Transforms/vregMachineLateInstrsCleanup.h>

#include <map>

#include <llvm/ADT/STLExtras.h>
#include <llvm/ADT/BitVector.h>
#include <llvm/ADT/PostOrderIterator.h>
#include <llvm/ADT/Statistic.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/CodeGen/TargetPassConfig.h>
#include <llvm/InitializePasses.h>
#include <llvm/Pass.h>
#include <llvm/CodeGen/GlobalISel/CSEInfo.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaCombinerHelper.h>

using namespace llvm;
using namespace hwtHls;
// because of INITIALIZE_PASS

#define DEBUG_TYPE "vreg-machine-latecleanup"

STATISTIC(NumRemoved, "Number of redundant instructions removed.");

namespace hwtHls {

class GISelInstProfileBuilderNoProfileDef: public GISelInstProfileBuilder {
public:
	using GISelInstProfileBuilder::GISelInstProfileBuilder;
	const GISelInstProfileBuilder&
	addNodeIDMachineOperand(const MachineOperand &MO) const {
		if (MO.isReg() && MO.isDef())
			return *this;
		return GISelInstProfileBuilder::addNodeIDMachineOperand(MO);
	}
	// copied GISelInstProfileBuilder::addNodeID because of addNodeIDMachineOperand
	const GISelInstProfileBuilder &
	addNodeID(const MachineInstr *MI) const {
	  addNodeIDMBB(MI->getParent());
	  addNodeIDOpcode(MI->getOpcode());
	  for (const auto &Op : MI->operands())
	    addNodeIDMachineOperand(Op);
	  addNodeIDFlag(MI->getFlags());
	  return *this;
	}
};

class UniqueMachineInstrNoProfileDef: public FoldingSetNode {
public:
	const MachineInstr *MI;
	explicit UniqueMachineInstrNoProfileDef(const MachineInstr *MI) : MI(MI) {}
	void Profile(FoldingSetNodeID &ID) {
		GISelInstProfileBuilderNoProfileDef(ID, MI->getMF()->getRegInfo()).addNodeID(
				MI);
	}
};

class VRegMachineLateInstrsCleanup: public MachineFunctionPass {
	const TargetRegisterInfo *TRI = nullptr;
	const TargetInstrInfo *TII = nullptr;
	MachineRegisterInfo *MRI = nullptr;

	BumpPtrAllocator UniqueInstrAllocator;
	std::unique_ptr<CSEConfigBase> CSEOpt;

	// same as GISelCSEInfo::getUniqueInstrForMI
	UniqueMachineInstrNoProfileDef* getUniqueInstrForMI(
			const MachineInstr *MI) {
		auto *Node = new (UniqueInstrAllocator) UniqueMachineInstrNoProfileDef(
				MI);
		return Node;
	}

	bool normalizeConstOperands(MachineIRBuilder &Builder, MachineInstr &MI);
	// Walk through the instructions in MBB and remove any redundant
	// instructions.
	bool processBlock(MachineBasicBlock &MBB);

	bool clearKillsForDef(Register Reg,
			std::map<Register, MachineInstr*>& lastKillInstr);
	bool isCandidate(const MachineInstr *MI, Register &DefedReg) const;

public:
	static char ID; // Pass identification, replacement for typeid

	VRegMachineLateInstrsCleanup() :
			MachineFunctionPass(ID) {
		initializeVRegMachineLateInstrsCleanupPass(
				*PassRegistry::getPassRegistry());
	}

	void getAnalysisUsage(AnalysisUsage &AU) const override {
		AU.addRequired<TargetPassConfig>();
		AU.setPreservesCFG();
		//AU.addRequired<MachineDominatorTree>();
		//AU.addPreserved<MachineDominatorTree>();
		//AU.addRequired<GISelCSEAnalysisWrapperPass>();
		//AU.addPreserved<GISelCSEAnalysisWrapperPass>();

		MachineFunctionPass::getAnalysisUsage(AU);
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

};

llvm::FunctionPass*
createVRegMachineLateInstrsCleanup() {
	return new VRegMachineLateInstrsCleanup();
}

char VRegMachineLateInstrsCleanup::ID = 0;

bool VRegMachineLateInstrsCleanup::runOnMachineFunction(MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;

	const auto &MFP = MF.getProperties();
	assert(
			!MFP.hasProperty(MachineFunctionProperties::Property::IsSSA)
					&& "If it has IsSSA use LLVM::MachineCSE");
	assert(
			!MFP.hasProperty(MachineFunctionProperties::Property::NoVRegs)
					&& "If it has NoVRegs use original LLVM::MachineLateInstrsCleanup");

	TRI = MF.getSubtarget().getRegisterInfo();
	TII = MF.getSubtarget().getInstrInfo();
	MRI = &MF.getRegInfo();
	auto *TPC = &getAnalysis<TargetPassConfig>();
	CSEOpt = TPC->getCSEConfig();
	// :note: can not use GISelCSEAnalysisWrapper because it hashes also dst registers

	bool Changed = false;
	// Visit all MBBs in an order that maximizes the reuse from predecessors.
	//ReversePostOrderTraversal<MachineFunction*> RPOT(&MF);
	for (MachineBasicBlock &MBB : MF)
		Changed |= processBlock(MBB);

	return Changed;
}

// Clear any previous kill flag on Reg found before I in MBB.
bool VRegMachineLateInstrsCleanup::clearKillsForDef(Register Reg,
		std::map<Register, MachineInstr*>& lastKillInstr) {
	// Kill flag in MBB
	auto KillMI = lastKillInstr.find(Reg);
	if (KillMI != lastKillInstr.end()) {
		KillMI->second->clearRegisterKills(Reg, TRI);
		lastKillInstr.erase(KillMI);
		return true;
	}
	return false;
}


// Return true if MI is a potential candidate for reuse/removal and if so
// also the register it defines in DefedReg.  A candidate is a simple
// instruction that does not touch memory, has only one register definition
// and the only reg it may use is FrameReg. Typically this is an immediate
// load or a load-address instruction.
bool VRegMachineLateInstrsCleanup::isCandidate(const MachineInstr *MI,
		Register &DefedReg) const {
	if (!CSEOpt->shouldCSEOpc(MI->getOpcode()) || (MI->getOpcode() == HwtFpga::HWTFPGA_MUX && MI->getNumExplicitOperands() == 2))
		return false;

	DefedReg = MCRegister::NoRegister;
	bool SawStore = true;
	if (!MI->isSafeToMove(nullptr, SawStore) || MI->isImplicitDef()
			|| MI->isInlineAsm() || MI->hasUnmodeledSideEffects())
		return false;
	for (unsigned i = 0, e = MI->getNumOperands(); i != e; ++i) {
		const MachineOperand &MO = MI->getOperand(i);
		if (MO.isReg()) {
			if (MO.isDef()) {
				if (i == 0 && !MO.isImplicit() && !MO.isDead())
					DefedReg = MO.getReg();
				else
					return false;
			} else if (!MO.getReg())
				return false;
		} else if (!(MO.isImm() || MO.isCImm() || MO.isFPImm() || MO.isCPI()
				|| MO.isGlobal() || MO.isSymbol()))
			return false;
	}
	return DefedReg.isValid();
}

bool VRegMachineLateInstrsCleanup::normalizeConstOperands(
		MachineIRBuilder &Builder, MachineInstr &MI) {
	// implements g_constant_to_imm combiner
	switch (MI.getOpcode()) {
	case TargetOpcode::G_PHI:
	case TargetOpcode::G_LOAD:
	case TargetOpcode::G_STORE:
	case TargetOpcode::G_ADD:
	case TargetOpcode::G_AND:
	case TargetOpcode::G_BR:
	case TargetOpcode::G_BRCOND:
	case TargetOpcode::G_ICMP:
	case TargetOpcode::G_PTR_ADD:
	case TargetOpcode::G_MUL:
	case TargetOpcode::G_UDIV:
	case TargetOpcode::G_SDIV:
	case TargetOpcode::G_UREM:
	case TargetOpcode::G_SREM:
	case TargetOpcode::G_OR:
	case TargetOpcode::G_SELECT:
	case TargetOpcode::G_SUB:
	case TargetOpcode::G_XOR:
	case TargetOpcode::G_SEXT:
	case TargetOpcode::G_ZEXT:
	case HwtFpga::HWTFPGA_EXTRACT:
	case HwtFpga::HWTFPGA_MERGE_VALUES:
	case HwtFpga::HWTFPGA_NOT:
	case HwtFpga::HWTFPGA_MUX:
	case HwtFpga::HWTFPGA_CLOAD:
	case HwtFpga::HWTFPGA_CSTORE:
	case HwtFpga::HWTFPGA_RET:
		if (HwtFpgaCombinerHelper::hasG_CONSTANTasUse(*MRI, MI)) {
			HwtFpgaCombinerHelper::rewriteG_CONSTANTasUseAsCImm(Builder,
					nullptr, MI);
			return true;
		}
	}
	return false;
}

bool regDiscard(std::map<Register, MachineInstr*>& regToInstr, Register Reg) {
	auto item = regToInstr.find(Reg);
	if (item != regToInstr.end()) {
		regToInstr.erase(item);
		return true;
	}
	return false;
}

bool VRegMachineLateInstrsCleanup::processBlock(MachineBasicBlock &MBB) {
	bool Changed = false;
	{
		MachineIRBuilder Builder(MBB, MBB.begin());
		for (auto &MI : make_early_inc_range(MBB)) {
			Changed |= normalizeConstOperands(Builder, MI);
		}
	}

	FoldingSet<UniqueMachineInstrNoProfileDef> CSEMap;
	// :see: CSEMIRBuilder::buildInstr
	std::map<Register, MachineInstr*> lastDefInstr;
	std::map<Register, MachineInstr*> lastKillInstr;
	std::map<Register, MachineInstr*> newBackupCopyOfReg;
	// Process MBB.
	//MachineFunction *MF = MBB->getParent();
	//const TargetRegisterInfo *TRI = MF->getSubtarget().getRegisterInfo();
	MachineIRBuilder Builder(MBB, MBB.begin());
	for (MachineInstr &MI : llvm::make_early_inc_range(MBB)) {
		Register DefedReg;
		bool IsCandidate = isCandidate(&MI, DefedReg);

		// Check for an earlier identical and reusable instruction.
		if (IsCandidate) {
			FoldingSetNodeID ID;
			GISelInstProfileBuilderNoProfileDef ProfBuilder(ID, *MRI);
			ProfBuilder.addNodeID(&MI);
			void *InsertPos = nullptr;
			UniqueMachineInstrNoProfileDef *_ExistingMI = CSEMap.FindNodeOrInsertPos(ID, InsertPos);
			if (_ExistingMI) {
				MachineInstr* ExistingMI = const_cast<MachineInstr* >(_ExistingMI->MI);
				LLVM_DEBUG(
						dbgs() << "Removing redundant instruction in "
								<< printMBBReference(MBB) << ":  " << MI
						;
				);
				MachineBasicBlock::iterator BkpCopyInsertPoint = ExistingMI->getNextNode()->getIterator();
				MachineBasicBlock::iterator AfterMiInsertPoint = MI.getNextNode()->getIterator();
				auto MiMO = MI.defs().begin();
				for (auto& ExistingMO: ExistingMI->defs()) {
					auto DefR = ExistingMO.getReg();
					auto lastDef = lastDefInstr.find(DefR);
					assert(lastDef != lastDefInstr.end() && "If there was record in CSEMap there must be also in lastDefInstr");
					Register DefReplacemntSrc = DefR;
					if (MiMO->isDead()) {
						// skip because result value is not used
						++MiMO;
						continue;
					}
					bool DefReplacemntSrcWasKill;
					if (lastDef->second != ExistingMI) {
						// there is some redef on the way from ExistingMI to MI
						// need to create a backup copy of dst register
						auto BkpCopy = newBackupCopyOfReg.find(DefR);
						if (BkpCopy != newBackupCopyOfReg.end()) {
							auto BkpCopyDst = BkpCopy->second->getOperand(0);
							BkpCopyDst.setIsDead(false);
							DefReplacemntSrc = BkpCopyDst.getReg();
							DefReplacemntSrcWasKill = clearKillsForDef(DefReplacemntSrc, lastKillInstr);
						} else {
							// [todo] clear any kill of DefR
							Builder.setInsertPt(MBB, BkpCopyInsertPoint);
							DefReplacemntSrcWasKill = clearKillsForDef(DefR, lastKillInstr);
							DefReplacemntSrc = MRI->cloneVirtualRegister(DefR);
							Builder.buildInstr(HwtFpga::HWTFPGA_MUX, {DefReplacemntSrc}, {DefR});
							BkpCopyInsertPoint = Builder.getInsertPt();
							if (ExistingMO.isDead()) {
								ExistingMO.setIsDead(false);
							}
						}
					} else {
						DefReplacemntSrcWasKill = clearKillsForDef(DefReplacemntSrc, lastKillInstr);
					}
					Builder.setInsertPt(MBB, AfterMiInsertPoint);
					auto NewCopy = Builder.buildInstr(HwtFpga::HWTFPGA_MUX, { MiMO->getReg() },
							{ DefReplacemntSrc });
					NewCopy.getInstr()->getOperand(1).setIsKill(DefReplacemntSrcWasKill);
					// [todo] if DefReplacemntSrc had kill set is there

					// update lastDefInstr and newBackupCopyOfReg
					lastDefInstr[MiMO->getReg()] = Builder.getInsertPt()->getPrevNode();
					auto BkpCopy = newBackupCopyOfReg.find(MiMO->getReg());
					if (BkpCopy != newBackupCopyOfReg.end()) {
						newBackupCopyOfReg.erase(BkpCopy);
					}

					AfterMiInsertPoint = Builder.getInsertPt();
				}
				MI.eraseFromParent();
				++NumRemoved;
				Changed = true;
				continue;
			} else {
				// This instruction does not exist in the CSEInfo.
				CSEMap.InsertNode(getUniqueInstrForMI(&MI), InsertPos);
			}
		}
		for (MachineOperand &MO : reverse(MI.operands())) {
			if (MO.isReg()) {
				Register Reg = MO.getReg();
				if (MO.isDef()) {
					lastDefInstr[Reg] = &MI;
					auto BkpCopy = newBackupCopyOfReg.find(Reg);
					if (BkpCopy != newBackupCopyOfReg.end()) {
						newBackupCopyOfReg.erase(BkpCopy);
					}
				} else if (MO.isKill()) {
					lastKillInstr[Reg] = &MI;
				}

			}
		}
	}

	return Changed;
}

}

INITIALIZE_PASS(VRegMachineLateInstrsCleanup, DEBUG_TYPE,
		"VReg Machine Late Instructions Cleanup Pass", false, false)
