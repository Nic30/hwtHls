#include <hwtHls/llvm/targets/Transforms/cheapBlockInlinePass.h>

#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/ADT/DenseMap.h>
#include <llvm/CodeGen/MachineLoopInfo.h>
#include <llvm/Analysis/TargetTransformInfo.h>
#include <llvm/ADT/SetVector.h>
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

#include <hwtHls/llvm/targets/hwtFpgaMCTargetDesc.h>
#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>
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
		AU.addRequired<MachineLoopInfoWrapperPass>();
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

namespace hwtHls {
bool isFreeMachineInstr(const MachineInstr &MI) {
	switch (MI.getOpcode()) {
	case TargetOpcode::COPY:
	case TargetOpcode::G_CONSTANT:
	case HwtFpga::HWTFPGA_MUX:
		return MI.getNumExplicitOperands() == 2;
		// :note: implicit defs should be hoisted before
	case TargetOpcode::G_IMPLICIT_DEF:
	case TargetOpcode::IMPLICIT_DEF:
	case HwtFpga::HWTFPGA_IMPLICIT_DEF:
	//	// [TODO]
	//	// case HwtFpga::HWTFPGA_EXTRACT:
	//	// case HwtFpga::HWTFPGA_MERGE_VALUES:
		return true;
	default:
		return false;
	}
}

bool isCheapMachineInstr(const MachineInstr &MI) {
	if (isFreeMachineInstr(MI))
		return true;
	switch (MI.getOpcode()) {
	case TargetOpcode::G_IMPLICIT_DEF:
	case TargetOpcode::IMPLICIT_DEF:
	case HwtFpga::HWTFPGA_IMPLICIT_DEF:
	case HwtFpga::HWTFPGA_MUX:
	case TargetOpcode::G_SELECT:
	case TargetOpcode::COPY:
	case TargetOpcode::G_CONSTANT:
	case HwtFpga::HWTFPGA_EXTRACT:
	case HwtFpga::HWTFPGA_MERGE_VALUES:
	case TargetOpcode::G_ICMP:
	case HwtFpga::HWTFPGA_ICMP:
	case TargetOpcode::G_AND:
	case TargetOpcode::G_OR:
	case TargetOpcode::G_XOR:
	case TargetOpcode::G_ADD:
	case TargetOpcode::G_SUB:
	case HwtFpga::HWTFPGA_AND:
	case HwtFpga::HWTFPGA_OR:
	case HwtFpga::HWTFPGA_XOR:
	case HwtFpga::HWTFPGA_NOT:
	case HwtFpga::HWTFPGA_ADD:
	case HwtFpga::HWTFPGA_SUB:
		return true;
	default:
		return false;
	}
}

bool MachineBasicBlock_isCheap_exceptTerminator(const MachineBasicBlock & MBB) {
	for (auto &MI : MBB) {
		if (MI.isTerminator())
			break;
		if (!isCheapMachineInstr(MI)) {
			return false;
		}
	}
	return true;
}

}
// :param MBB: block which is going to be removed
void removeMachineBasicBlockWithSingleSuccessor(MachineBasicBlock &MBB, MachineBasicBlock &MBBReplacement,
		const SmallVectorImpl<MachineBasicBlock*> &MBB_predecessors) {
	auto& MF = *MBB.getParent();
	assert(&MBB != &*MF.begin() && "Can not remove entry block");
	assert(&MBB != &MBBReplacement);
	auto prevBlock = MBB.getPrevNode();
	
	// need to construct explicit branch if the previous block had implicit fallthrough
	if (auto *FallThrough = prevBlock->getFallThrough()) {
		if (FallThrough == &MBB) {
			MachineIRBuilder B(*prevBlock, prevBlock->end());
			// [todo] consider using
			//  TII->insertBranch();
			B.buildInstr(HwtFpga::HWTFPGA_BR).addMBB(&MBBReplacement);
		}
	}

	// update terminators in predecessor blocks to jump to only successor
	for (MachineBasicBlock *Pred : MBB_predecessors) {
		for (MachineInstr &Term : Pred->terminators()) {
			for (auto &MO : Term.operands()) {
				if (MO.isMBB() && MO.getMBB() == &MBB) {
					MO.setMBB(&MBBReplacement);
				}
			}
		}
		// :attention: replaceSuccessor does only replace in block successors, but not in branch instructions
		Pred->replaceSuccessor(&MBB, &MBBReplacement);
	}
	

	// based on BranchFolder::RemoveDeadBlock
	assert(MBB.pred_empty() && "MBB must be dead!");
	LLVM_DEBUG(dbgs() << "\nRemoving MBB: " << MBB);

	// drop all successors.
	while (!MBB.succ_empty())
		MBB.removeSuccessor(MBB.succ_end() - 1);

	// Update call info.
	for (const MachineInstr &MI : MBB)
	  if (MI.shouldUpdateAdditionalCallInfo())
	    MF.eraseAdditionalCallInfo(&MI);

	// Remove the block.
	// :note: based on IRTranslator::runOnMachineFunction
	MF.remove(&MBB);
	// MF.erase(&MBB);
	MF.deleteMachineBasicBlock(&MBB);
	assert(!is_contained(MBBReplacement.predecessors(), &MBB));
}

void copyMachineBlockContentToPredecessor(
	MachineRegisterInfo &MRI, const TargetInstrInfo &TII,
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
			if (!MRI.getType(C.getReg()).isValid())
				MRI.setType(C.getReg(), LLT::scalar(1));

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
	
	hwtHls::bimap<llvm::Register, llvm::Register> regsForSpeculation;
	// register needs to be predicated if it is liveout if any predecessor of MBB
	std::array<MachineOperand, 2> Cond = {
		MachineOperand::CreateReg((toMBBBrCond.has_value() ? toMBBBrCond.value() : Register(0)), false), // 0 is dummy value when unused
		MachineOperand::CreateImm(0), // = not negated
	};
	auto & MF = *MBB.getParent(); 
	auto predIP= Pred->getFirstTerminator();
	for (auto &_MI : MBB) {
		if (_MI.isTerminator())
			break;
		auto& MI = *MF.CloneMachineInstr(&_MI);
		Pred->insert(predIP, &MI);
		if (toMBBBrCond.has_value()) {
			if (!TII.PredicateInstruction(MI, Cond)) {
				hwtHls::predicateInstructionUsingDefRegRename(
					MRI, VRegLiveins, MI, regsForSpeculation);
			}
		} // else no need to conditionally (speculatively) execute this instr
	}
	
	if (!regsForSpeculation.empty())
		createSpeculationMergeMuxes(*Pred, predIP, regsForSpeculation, Cond, MRI);
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

// merge L1 into L0 (child into parent)
void mergeMachineLoops(MachineLoopInfo &LI, MachineBasicBlock &MBB,
					   MachineBasicBlock &MBBSucc, MachineLoop *L0,
					   MachineLoop *L1) {
	// Merge the loops. (L1 into L0)
	SmallVector<MachineBasicBlock *, 8> Blocks(L1->blocks());
	for (MachineBasicBlock *BB : Blocks) {
		// :note: may contain if L1 is inside of L0
		assert(L0->contains(BB) &&
			   "Must contain because L1 should be nested in L0");
		//	L0->addBlockEntry(BB);
		L1->removeBlockFromLoop(BB);
		if (LI.getLoopFor(BB) != L1)
			continue;
		LI.changeLoopFor(BB, L0);
	}
	while (!L1->isInnermost()) {
		const auto &ChildLoopIt = L1->begin();
		auto *ChildLoop = *ChildLoopIt;
		L1->removeChildLoop(ChildLoopIt);
		L0->addChildLoop(ChildLoop);
	}
	// Delete the now empty loop L1.
	// LI.removeLoop(L1);
}

bool CheapBlockInline::runOnMachineFunction(MachineFunction &MF) {
	if (skipFunction(MF.getFunction()))
		return false;

	bool Changed = false;

	TRI = MF.getSubtarget().getRegisterInfo();
	TII = MF.getSubtarget().getInstrInfo();
	MRI = &MF.getRegInfo();
	VRegLiveins = &getAnalysis<hwtHls::HwtHlsVRegLiveins>();
	MachineLoopInfo &Loops = getAnalysis<MachineLoopInfoWrapperPass>().getLI();

	for (MachineBasicBlock &MBB : make_early_inc_range(MF)) {
		if (&MBB == &*MF.begin())
			continue; // can not remove entry block
		if (MBB.succ_size() != 1)
			continue;
		if (*MBB.succ_begin() == &MBB)
			// if self loop
			continue;
		bool isFree = true;
		bool isCheap = true;
		MachineBasicBlock& MBBSuc = *MBB.getSingleSuccessor();	 
		// allow this only for loop pre-headers

		MachineLoop * MBBLoop = Loops.getLoopFor(&MBB);
		if (!MBBLoop || MBBLoop->getHeader() != &MBB)
			continue;
		MachineLoop * MBBSuccLoop = Loops.getLoopFor(&MBBSuc);
		if (!MBBSuccLoop || MBBSuccLoop->getHeader() != &MBBSuc)
			continue;
		assert(MBBLoop->contains(&MBBSuc));
					
		for (auto &MI : MBB) {
			if (MI.isTerminator()) {
				break;
			}
			if (!isFree || !hwtHls::isFreeMachineInstr(MI)) {
				isFree = false;
				if (!isCheap || !hwtHls::isCheapMachineInstr(MI)) {
					isCheap = false;
					break;
				}
			}
		}
		if (isFree || isCheap) {
			SmallVector<MachineBasicBlock *, 8> MBB_predecessors(
				MBB.predecessors());
			for (MachineBasicBlock *Pred : MBB_predecessors) {
				copyMachineBlockContentToPredecessor(*MRI, *TII, *VRegLiveins, MBB, Pred);
			}
			// :attention: alls MF->erase(&MBB);
			removeMachineBasicBlockWithSingleSuccessor(MBB, MBBSuc, MBB_predecessors);
			mergeMachineLoops(Loops, MBB, MBBSuc, MBBLoop, MBBSuccLoop);
			MBBLoop->moveToHeader(&MBBSuc);
			Loops.removeBlock(&MBB);
			VRegLiveins->removeBlock(&MBB);

			for (MachineBasicBlock *Pred : MBB_predecessors) {
				MachineBasicBlockOptimizeTerminator(*Pred);
			}
			
			Changed = true;
		} 
		//else if (isCheap) {
		//	errs() << "MBB CheapBlockInline: " << MBB.getFullName() << "\n";
		//	MF.dump();
		//	errs() << "\n";
		//	// merge predicated into single successor
		//	Changed |= mergePredicatedBBToSingleSuccessor(*MRI, *TII, *TRI, *VRegLiveins, MBB);
		//	errs() << "after CheapBlockInline mergePredicatedBBToSingleSuccessor:\n";
		//	MF.dump();
		//	errs() << "\n"; 
		//	/// MF.verify(this, "CheapBlockInline mergePredicatedBBToSingleSuccessor", &errs());
		//}
	}
	if (Changed)
		MF.RenumberBlocks();
	return Changed;
}

namespace hwtHls {
FunctionPass* createCheapBlockInlinePass() {
	return new CheapBlockInline();
}
}
