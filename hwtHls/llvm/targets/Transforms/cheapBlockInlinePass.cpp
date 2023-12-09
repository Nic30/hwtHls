#include <hwtHls/llvm/targets/Transforms/cheapBlockInlinePass.h>

#include <llvm/ADT/STLExtras.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineInstr.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/CodeGen/TargetRegisterInfo.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/InitializePasses.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>

using namespace llvm;

#define DEBUG_TYPE "hwthls-cheapblockinline"

namespace {

class CheapBlockInline: public MachineFunctionPass {
	const TargetRegisterInfo *TRI;
	const TargetInstrInfo *TII;
	MachineRegisterInfo *MRI;
	hwtHls::HwtHlsVRegLiveins *VRegLiveins;

public:
	static char ID; // Pass identification, replacement for typeid

	CheapBlockInline() :
			MachineFunctionPass(ID), TRI(nullptr), TII(nullptr), MRI(nullptr), VRegLiveins(
					nullptr) {
		initializeCheapBlockInlinePass(*PassRegistry::getPassRegistry());
	}

	void getAnalysisUsage(AnalysisUsage &AU) const override {
		AU.addRequired<hwtHls::HwtHlsVRegLiveins>();
		MachineFunctionPass::getAnalysisUsage(AU);
	}

	bool runOnMachineFunction(MachineFunction &MF) override;

	MachineFunctionProperties getRequiredProperties() const override {
		MachineFunctionProperties p;
		p.set(MachineFunctionProperties::Property::Legalized); // legalized because this pass generates HwtFpga instructions
		p.set(MachineFunctionProperties::Property::NoPHIs); // no PHIs because this pass do not update them
		return p;
	}

};

} // end anonymous namespace

char CheapBlockInline::ID = 0;

INITIALIZE_PASS(CheapBlockInline, DEBUG_TYPE, "Cheap Machine Block Inline Pass",
		false, false)

bool isFreeMachineInstr(const MachineInstr &MI) {
	switch (MI.getOpcode()) {
	case HwtFpga::HWTFPGA_MUX:
		return MI.getNumExplicitOperands() == 2;
		// :note: implicit defs should be hoisted before
		// case TargetOpcode::G_IMPLICIT_DEF:
		// case TargetOpcode::IMPLICIT_DEF:
		// [TODO]
		// case TargetOpcode::COPY:
		// case TargetOpcode::G_CONSTANT:
		// case HwtFpga::HWTFPGA_EXTRACT:
		// case HwtFpga::HWTFPGA_MERGE_VALUES:
		return true;
	default:
		return false;
	}
}

void removeMachineBasicBlockWithSingleSuccessor(MachineBasicBlock &MBB,
		const SmallVectorImpl<MachineBasicBlock*> &MBB_predecessors) {

	// update terminators in predecessor blocks to jump to only successor
	MachineBasicBlock &MBBReplacement = **MBB.succ_begin();
	for (MachineBasicBlock *Pred : MBB_predecessors) {
		for (MachineInstr &Term : Pred->terminators()) {
			for (auto &MO : Term.operands()) {
				if (MO.isMBB() && MO.getMBB() == &MBB) {
					MO.setMBB(&MBBReplacement);
				}
			}
		}
		if (auto *FallThrough = Pred->getFallThrough()) {
			if (FallThrough == &MBB) {
				MachineIRBuilder B(*Pred, Pred->end());
				B.buildInstr(HwtFpga::HWTFPGA_BR).addMBB(&MBBReplacement);
			}
		}
		Pred->replaceSuccessor(&MBB, &MBBReplacement);
	}

	// based on BranchFolder::RemoveDeadBlock
	assert(MBB.pred_empty() && "MBB must be dead!");
	LLVM_DEBUG(dbgs() << "\nRemoving MBB: " << MBB);

	MachineFunction *MF = MBB.getParent();
	// drop all successors.
	while (!MBB.succ_empty())
		MBB.removeSuccessor(MBB.succ_end() - 1);

	// Update call site info.
	for (const MachineInstr &MI : MBB)
		if (MI.shouldUpdateCallSiteInfo())
			MF->eraseCallSiteInfo(&MI);

	// Remove the block.
	MF->erase(&MBB);
}

void copyMachineBlockContentToPredecessor(MachineRegisterInfo &MRI,
		hwtHls::HwtHlsVRegLiveins &VRegLiveins, MachineBasicBlock &MBB,
		MachineBasicBlock *Pred) {
	// copy self instructions to predecessors
	// with a MUX which is enabled when the original branch was targeting this MBB
	// replace MBB with SuccMBB, remove MBB
	// optimize branches in original MBB predecessors
	MachineBasicBlock::iterator PredTerm = Pred->terminators().begin();
	MachineIRBuilder B(*Pred, PredTerm);

	std::optional<Register> toMBBBrCond;
	for (MachineInstr &Term : Pred->terminators()) {
		bool searchEnd = false;
		switch (Term.getOpcode()) {
		case HwtFpga::HWTFPGA_BR:
		case TargetOpcode::G_BR:
			searchEnd = true;
			break;

		case HwtFpga::HWTFPGA_BRCOND:
		case TargetOpcode::G_BRCOND: {
			auto C = Term.getOperand(0);
			auto Dst = Term.getOperand(1);
			assert(C.isReg());
			assert(!C.isUndef());
			assert(Dst.isMBB());
			bool isMbb = Dst.getMBB() == &MBB;
			Register BrC;
			if (isMbb) {
				BrC = C.getReg();
			} else {
				BrC = MRI.cloneVirtualRegister(C.getReg());
				auto BrC_n = B.buildNot(BrC, C.getReg()); // builds xor 1
				assert(BrC_n.getInstr()->getOpcode() == TargetOpcode::G_XOR);
				MRI.setRegClass(BrC_n.getInstr()->getOperand(2).getReg(),
						&HwtFpga::anyregclsRegClass);
			}
			if (toMBBBrCond.has_value() && toMBBBrCond.value() != BrC) {
				Register BrC2 = MRI.cloneVirtualRegister(BrC);
				B.buildAnd(BrC2, toMBBBrCond.value(), BrC);
				toMBBBrCond = BrC2;
			} else {
				toMBBBrCond = BrC;
			}

			if (isMbb) {
				// if this jumps to the MBB block we discovered out the condition
				searchEnd = true;
			}
			break;

		}
		default:
			Term.dump();
			llvm_unreachable("Unknown terminator");
		}
		if (searchEnd)
			break;
	}
	// copy content (excluding terminators) of MBB to all predecessors
	for (auto &MI : MBB) {
		if (MI.isTerminator()) {
			break;
		}
		switch (MI.getOpcode()) {
		case HwtFpga::HWTFPGA_MUX: {
			// convert copy to conditional copy
			auto dstReg = MI.getOperand(0).getReg();
			bool hasOneDef = MRI.hasOneDef(dstReg);
			auto MIB = B.buildInstr(HwtFpga::HWTFPGA_MUX);
			assert(MI.getNumOperands() == 2);
			for (auto &MO : MI.operands()) {
				MIB.add(MO);
			}
			if (!hasOneDef && VRegLiveins.isLiveout(*Pred, dstReg)
					&& toMBBBrCond.has_value()) {
				MIB.addUse(toMBBBrCond.value());
				MIB.addUse(MI.getOperand(0).getReg());
			}
			break;
		}
		default:
			MI.dump();
			llvm_unreachable(
					"Unexpected instruction (the block should have already been check if it is compatible)");
		}
	}
}

void MachineBasicBlockOptimizeTerminator(MachineBasicBlock &MBB) {
	MachineBasicBlock *last = MBB.getFallThrough();
	SmallVector<MachineInstr*> toRm;
	for (MachineInstr &T : reverse(MBB.terminators())) {
		assert(T.isTerminator());
		if (T.isConditionalBranch()) {
			auto *dst = T.getOperand(1).getMBB();
			if (last != nullptr && dst == last) {
				// conditional jump to same target as previous unconditional jump
				toRm.push_back(&T);
			} else {
				break;
			}
		} else if (T.isUnconditionalBranch()) {
			if (last != nullptr && T.getOperand(0).getMBB() == last) {
				// unconditional jump to same target as previous unconditional jump
				toRm.push_back(&T);
			} else {
				last = T.getOperand(0).getMBB();
			}
		} else {
			T.dump();
			llvm_unreachable("Unexpected branch instruction");
		}
	}
	for (auto *T : toRm) {
		T->eraseFromParent();
	}
}

bool CheapBlockInline::runOnMachineFunction(MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;

	bool Changed = false;

	TRI = MF.getSubtarget().getRegisterInfo();
	TII = MF.getSubtarget().getInstrInfo();
	MRI = &MF.getRegInfo();
	VRegLiveins = &getAnalysis<hwtHls::HwtHlsVRegLiveins>();

	for (MachineBasicBlock &MBB : make_early_inc_range(MF)) {
		if (&MBB == &*MF.begin())
			continue; // can not remove entry block
		bool isFree = true;
		for (auto &MI : MBB) {
			if (MI.isTerminator()) {
				break;
			}
			if (!isFreeMachineInstr(MI)) {
				isFree = false;
				break;
			}
		}
		if (isFree) {
			if (MBB.succ_size() == 1 && *MBB.succ_begin() != &MBB) {
				SmallVector<MachineBasicBlock*, 8> MBB_predecessors(
						MBB.predecessors());
				for (MachineBasicBlock *Pred : MBB_predecessors) {
					copyMachineBlockContentToPredecessor(*MRI, *VRegLiveins,
							MBB, Pred);
				}

				removeMachineBasicBlockWithSingleSuccessor(MBB,
						MBB_predecessors);

				for (MachineBasicBlock *Pred : MBB_predecessors) {
					MachineBasicBlockOptimizeTerminator(*Pred);
				}
				//MBB.eraseFromParent();
				Changed = true;
			}
		}
	}

	return Changed;
}

namespace hwtHls {
FunctionPass* createCheapBlockInlinePass() {
	return new CheapBlockInline();
}
}
