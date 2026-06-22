#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <hwtHls/llvm/targets/Analysis/registerBitWidth.h>
#include <hwtHls/llvm/targets/Transforms/cheapBlockInlinePass.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaMCTargetDesc.h>
#include <llvm/CodeGen/Register.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <llvm/Support/ErrorHandling.h>

using namespace llvm;
using namespace hwtHls;

namespace hwtHls {
	
VRegIfConverter::BBInfo& VRegIfConverter::forceBlockReAnalysis(MachineBasicBlock & MBB) {
	auto &BBI = BBAnalysis[MBB.getNumber()];
	assert(BBI.BB == &MBB);
	auto origIsDone = BBI.IsDone;
	// required for AnalyzeBranches, all blocks are done when calling this
	// function, now we are trying to find another blocks which are not
	// covered by main analysis
	BBI.IsDone = false;
	AnalyzeBranches(BBI);
	BBI.IsDone = origIsDone;
	return BBI;
}


bool VRegIfConverter::tryMergeIntoSingleSuccessor(llvm::MachineFunction &MF, llvm::MachineDomTreeUpdater & MDTU, llvm ::Statistic & numCntr) {
	bool Change = false;
	for (auto &MBB : make_early_inc_range(MF)) {
		auto &BBI = BBAnalysis[MBB.getNumber()];
		if (!BBI.IsBrAnalyzable)
			continue;

		auto suc = BBI.BB->getSingleSuccessor();
		if (!suc)
			continue;
		if (suc == BBI.BB)
			continue;
		
		if (MDTU.getDomTree().dominates(suc, &MBB))
			continue; // avoid merging loop latch to header

		if (!MachineBasicBlock_isCheap_exceptTerminator(MBB))
			continue;

		if (suc->pred_size() == 1) {
			// too simple for this rule, BranchFolding should handle this case
			continue;
		}

		if (IfConvertIntoSuccessor(BBI, *suc, MDTU)) {
			++numCntr;
			Change = true; 
			break; // because we want to prioritize other rules first as this has higher overhead
		}
	}

	return Change;
}

void VRegIfConverter::_IfConvertIntoSuccessor_predefUndefLiveins(MachineIRBuilder& Builder, MachineBasicBlock &MBB,
	 MachineBasicBlock & MBBSucc) {
	auto &MF = *MBB.getParent();
	auto &MBBLiveIns = VRegLiveins->liveins(MBB);
	// predef all MBB liveins in MBBSucc predecessors where the livein is
	// not defined
	for (auto *SucPred : MBBSucc.predecessors()) {
		if (SucPred == &MBB) {
			continue;
		}
		// auto &SucPredLiveIns = VRegLiveins->liveins(*SucPred);
		Builder.setInsertPt(*SucPred, SucPred->getFirstTerminator());
		for (Register r : MBBLiveIns) {
			if (// SucPredLiveIns.contains(r) &&
				!VRegLiveins->isLiveout(*SucPred, r)) {
				auto llt = MRI->getType(r);
				if (!llt.isValid()) {
					// lazy load HwtFpgaRegisterBitWidth only if necessary
					HwtFpgaRegisterBitWidth().runOnMachineFunction(MF);
					llt = MRI->getType(r);
					assert(llt.isValid());
				}
				MachineInstrBuilder MIB =
					Builder.buildInstr(HwtFpga::HWTFPGA_IMPLICIT_DEF);
				MIB.addDef(r);
				MIB.addImm(llt.getSizeInBits());
			}
		}
	}

	auto & MBBSuccLiveIns = VRegLiveins->liveins(MBBSucc);
	//{
	//	errs() << "MBBSuccLiveIns: [";
	//	for (Register r : MBBSuccLiveIns) {
	//		errs() << r.virtRegIndex() << ", ";
	//	}
	//	errs() << "]\n";
	//
	//	SmallSet<Register, 32> liveinsProvidedByMBB;
	//	for (Register r : VRegLiveins->liveins(MBBSucc)) {
	//		if (!VRegLiveins->liveins(MBB).contains(r))
	//			liveinsProvidedByMBB.insert(r);
	//	}
	//	errs() << "liveinsProvidedByMBB: [";
	//	for (Register r : liveinsProvidedByMBB) {
	//		errs() << r.virtRegIndex() << ", ";
	//	}
	//	errs() << "]\n";
	//}
	
	// predef all MBBSucc liveins in MBB predecessors where the livein is
	// not defined if not defined in MBB
	for (auto *Pred : MBB.predecessors()) {
		if (Pred == &MBB) {
			continue;
		}
		// errs() << "Pred: ";
		// Pred->printAsOperand(errs());
		// errs() << "\n";
		Builder.setInsertPt(*Pred, Pred->getFirstTerminator());
		for (Register r : MBBSuccLiveIns) {
			// :note: even if the r is defined in MBB we need to predef it as the MBBSucc can be header of the loops
			//        and thus MBB defs needs to be captured during the first iteration
			if (!VRegLiveins->isLiveout(*Pred, r)) {
				auto llt = MRI->getType(r);
				if (!llt.isValid()) {
					// lazy load HwtFpgaRegisterBitWidth only if necessary
					HwtFpgaRegisterBitWidth().runOnMachineFunction(MF);
					llt = MRI->getType(r);
					assert(llt.isValid());
				}
				MachineInstrBuilder MIB =
					Builder.buildInstr(HwtFpga::HWTFPGA_IMPLICIT_DEF);
				MIB.addDef(r);
				MIB.addImm(llt.getSizeInBits());
			}
		}
	}
}

Register VRegIfConverter::
	_IfConvertIntoSuccessor_defineConditionOnEndOfEachNewPredecessor(
		MachineIRBuilder &Builder, MachineBasicBlock &MBB,
		MachineBasicBlock &MBBSucc) {
	auto &MF = *MBB.getParent();
	auto &Ctx = MF.getFunction().getContext();
	// 1 if MBB instructions should be activated
	Register CondReg = MRI->createVirtualRegister(&HwtFpga::anyregclsRegClass);
	MRI->setType(CondReg, LLT::scalar(1));
	SetVector<MachineBasicBlock *> newPreds;
	newPreds.insert_range(MBB.predecessors());
	for (auto *SucPred : MBBSucc.predecessors()) {
		if (SucPred == &MBB)
			continue;
		newPreds.insert(SucPred);
	}

	// construct MBB en codition set at then end of future MBBSucc predecessors
	for (auto *PredMBB : newPreds) {
		auto &PredBBI = forceBlockReAnalysis(*PredMBB);
		MachineBasicBlock::iterator PredTerm =
			PredBBI.BB->terminators().begin();
		Builder.setInsertPt(*PredBBI.BB, PredTerm);
		bool TisMBB;
		bool FisMBB = false;
		auto fallThrough = PredBBI.BB->getFallThrough();
		if (PredBBI.TrueBB) {
			TisMBB = PredBBI.TrueBB == &MBB;
			FisMBB = PredBBI.FalseBB == &MBB ||
					 (!PredBBI.FalseBB && fallThrough == &MBB);
		} else {
			assert(PredBBI.HasFallThrough);
			TisMBB = fallThrough == &MBB;
		}
		std::optional<MachineOperand> condVal;
		if (PredBBI.FalseBB) {
			if ((TisMBB && FisMBB) || (!TisMBB && !FisMBB)) {
				condVal = MachineOperand::CreateCImm(
					ConstantInt::getBool(Ctx, TisMBB));
			} else {
				if (!TisMBB) {
					TII->reverseBranchCondition(PredBBI.BrCond);
				}
				// 1 if MBB is going to be entered
				// apply potential negation
				assert(PredBBI.BrCond.size() == 2);
				bool isNegated = PredBBI.BrCond[1].getImm();
				if (isNegated) {
					auto Cond_n = hwtHls::negateRegister(
						*MRI, TRI, Builder, PredBBI.BrCond[0].getReg());
					condVal = MachineOperand::CreateReg(Cond_n, false);
				} else {
					condVal = PredBBI.BrCond[0];
				}
			}
		} else {
			condVal =
				MachineOperand::CreateCImm(ConstantInt::getBool(Ctx, TisMBB));
		}
		auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
		MIB.addDef(CondReg);
		MIB.add(condVal.value());
	}
	return CondReg;
}

bool VRegIfConverter::IfConvertIntoSuccessor(BBInfo &BBI,
											 llvm::MachineBasicBlock &MBBSucc,
											 MachineDomTreeUpdater &MDTU) {
	// For registers which are not used only internally in the block we have to
	// create a speculation/predication logic,
	// predicateInstructionUsingDefRegRename will be used to predicate
	// unpredicable instructions which may be speculated
	// * the finalization mux requires def of original register value,
	//    * This is a problem as the value may not be available in
	//      MBBSucc, we need the def even if it will not be used because
	//      MBB instructions will not be executed
	//    * In each predecessor of MBBSucc which are not MBB predecessor or MBB
	//      itself if the reg is not liveout of that reg we need to construct
	//      a def which will be
	//

	// CopyAndPredicateBlock(BBI, *CvtBBI, Cond, CvtMBBEndsWithRet);
	auto &MBB = *BBI.BB;
	Redefs.init(*TRI, *VRegLiveins);

	if (MRI->tracksLiveness()) {
	  // Initialize liveins to the first BB. These are potentially redefined by
	  // predicated instructions.
	  Redefs.addLiveInsNoPristines(MBB);
	  Redefs.addLiveInsNoPristines(MBBSucc);
	}

	auto &MF = *MBB.getParent();
	auto KindName = IfcvtKind_toStr(IfcvtKind::ICIntoSingleSucc);
	if (enableTrace)
	  hwtHls::writeCFGToDotFile(MF, std::string("IC.") + std::to_string(dbgCntr++) + KindName +  + "-before.dot");
	//errs() << "[dbg] IfConvertIntoSuccessor \n";
	//MBB.printAsOperand(errs());
	//MF.dump();
	//errs() << "\n";
	// at the end of each MBB and MBBSucc predecessor define
	// a condition which will be 1 if original MBB was jumped into
	
	MachineIRBuilder Builder(MF);
	_IfConvertIntoSuccessor_predefUndefLiveins(Builder, MBB, MBBSucc);
	Register CondReg = _IfConvertIntoSuccessor_defineConditionOnEndOfEachNewPredecessor(Builder, MBB, MBBSucc);

	// register needs to be predicated if it is not private to this block or is
	// its livein register is private to this block if all defs and uses are in
	// this block
	//    (def before use automatically implies that reg can not be livein)
	//    (this also implies that the reg is private if it is not liveins or
	//    liveouts)
	std::array<MachineOperand, 2> Cond = {
		MachineOperand::CreateReg(CondReg, false),
		MachineOperand::CreateImm(0), // = not negated
	};
	hwtHls::bimap<llvm::Register, llvm::Register> regsForSpeculation;
	auto & MBBSuccLiveins = VRegLiveins->liveinsMutable(MBBSucc);
	// VRegLiveins->addToLivenessRecursively(MBBSucc, CondReg);
	MBBSuccLiveins.insert(CondReg);
	MachineOperand* lastUseOfCondReg = nullptr;
	for (auto &MI : MBB) {
		if (MI.isTerminator())
			break;
		if (!TII->PredicateInstruction(MI, Cond)) {
			hwtHls::predicateInstructionUsingDefRegRename(
				*MRI, *VRegLiveins, MI, regsForSpeculation,
				hwtHls::predicateInstructionUsingDefRegRename_defNeedsTmpRegPredicate_predToSuc);
		}
		// discard kills of MBBSucc liveins
		for (auto& MO: MI.uses()) {
			if (!MO.isReg()) {
			    continue;
			}
			if (MO.getReg() == CondReg) {
				lastUseOfCondReg = &MO;
			}
			if (MO.isKill()) {
				if (MBBSuccLiveins.contains(MO.getReg())) {
					MO.setIsKill(false);
				}
			}
		}
	}
	// copy MBB except terminators to MBBSucc begin
	auto ToTI = MBBSucc.getFirstNonDebugInstr();
	auto FromEndTI = MBB.getFirstTerminator();
	MBBSucc.splice(ToTI, &MBB, MBB.begin(), FromEndTI);

	if (!regsForSpeculation.empty()) {
		auto lastMux = createSpeculationMergeMuxes(MBBSucc, ToTI, regsForSpeculation, Cond,
									*MRI);
		if (lastMux) {
			lastUseOfCondReg = &lastMux->getOperand(2);
			assert(lastUseOfCondReg->getReg() == CondReg);
		}
	}
	if (lastUseOfCondReg) {
		lastUseOfCondReg->setIsKill(true);
	}
	auto & MBBLiveIns = VRegLiveins->liveinsMutable(MBB);
	for (auto r: MBBLiveIns) {
		MBBSuccLiveins.insert(r);
	}
	InvalidatePreds(MBB);
	InvalidateSuccs(MBB);
	InvalidatePreds(MBBSucc);
	InvalidateSuccs(MBBSucc);
	using DTUpdateKind = MachineDominatorTree::UpdateKind;
	SmallVector<MachineDomTreeUpdater::UpdateT> MDTUpdates;
	// disconnect MBB form CFG and delete it
	SmallVector<MachineBasicBlock *> MBBPreds(MBB.predecessors());
	for (auto *PredMBB : MBBPreds) {
		assert(PredMBB != &MBB);
		// BBInfo & BBI = *bbis[PredMBB];
		//  :attention: replaceSuccessor does only replace in block successors,
		// but not in branch instructions
		PredMBB->ReplaceUsesOfBlockWith(&MBB, &MBBSucc);
		Builder.setInsertPt(*PredMBB, PredMBB->end());
		if (!blockNeverFallThrough(forceBlockReAnalysis(*PredMBB)) && PredMBB->getNextNode() == &MBB) {
			// assert(!BBI.TrueBB || (!BBI.BrCond.empty() && !BBI.FalseBB));
			auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_BR);
			MIB.addMBB(&MBBSucc);
		}
		MDTUpdates.push_back({DTUpdateKind::Delete, PredMBB, &MBB});
		MDTUpdates.push_back({DTUpdateKind::Insert, PredMBB, &MBBSucc});
	}
	// VRegLiveins->removeBlock(&MBB);
	MBB.removeSuccessor(&MBBSucc);
	MDTUpdates.push_back({DTUpdateKind::Delete, &MBB, &MBBSucc});
	MDTU.applyUpdates(MDTUpdates);
	MBB.clear();
	// MBB.eraseFromParent();
	VRegLiveins->recompute();
	//errs() << "[dbg] IfConvertIntoSuccessor after\n";
	//MF.dump();
	//errs() << "\n";
	if (enableTrace)
	  hwtHls::writeCFGToDotFile(MF, std::string("IC.") + std::to_string(dbgCntr++) + KindName +  + "-after.dot");
	onChangeTestCallback("IfConvertIntoSuccessor", MF);
	return true;
}

}
