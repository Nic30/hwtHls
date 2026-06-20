#include <hwtHls/llvm/targets/Analysis/VRegLiveins.h>
#include <hwtHls/llvm/targets/Transforms/vregIfConversionPriv.h>

#include <hwtHls/llvm/targets/Analysis/registerBitWidth.h>
#include <hwtHls/llvm/targets/Transforms/cheapBlockInlinePass.h>
#include <hwtHls/llvm/targets/Transforms/vregConditionUtils.h>
#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaMCTargetDesc.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/CodeGen/MachineDominators.h>
#include <llvm/IR/CFG.h>
#include <llvm/CodeGen/MachineDomTreeUpdater.h>
#include <llvm/CodeGen/MachineRegisterInfo.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/CodeGen/GlobalISel/MachineIRBuilder.h>
#include <llvm/CodeGen/MachineBasicBlock.h>
#include <llvm/CodeGen/MachineInstrBuilder.h>
#include <llvm/CodeGen/MachineOperand.h>
#include <llvm/CodeGen/Register.h>
#include <llvm/Support/ErrorHandling.h>

using namespace llvm;
using namespace hwtHls;

namespace hwtHls {

static void addInSectionSuccessorsToSetTransitively(MachineBasicBlock &MBB,
													VRegIfConverter::MBBlockSet &sectionBlocks,
													VRegIfConverter::MBBlockSet &result) {
	for (auto suc : MBB.successors()) {
		if (!sectionBlocks.contains(suc))
			continue;
		if (result.insert(suc)) {
			addInSectionSuccessorsToSetTransitively(*suc, sectionBlocks,
													result);
		}
	}
}

// :note: MBBBottom will not be part of the section
// [todo] allow to be part of the section as a top
bool VRegIfConverter::CheapPredSectionFind(
	MachineDominatorTree &MDT, MachineBasicBlock &MBBBottom,
	VRegIfConverter::MBBlockSet &sectionBlocks,
	VRegIfConverter::MBBlockSet &blocksForPredication,
	VRegIfConverter::MBBlockSet &blocksForBrPredication) {
	// transitively add predecessors to sectionBlocks only if
	//  * the block is cheap
	// * If the block has some successor from the region and also jump to MBB we
	// remove this jump and instead
	//   jump to in region successor and disable it transitively until MBB is
	//   reached
	
	// errs() << "tryCheapPredSectionBrCondPruning MBBBottom: ";
	// MBBBottom.printAsOperand(errs()); 
	// errs() << "\n";

	SmallSetVector<MachineBasicBlock *, 16>
		sectionBlocksTmp; // may contain also too simple CFG blocks
	SmallSetVector<MachineBasicBlock *, 16> worklist;
	for (auto Pred : MBBBottom.predecessors()) {
		worklist.insert(Pred);
	}
	while (!worklist.empty()) {
		auto &MBB = *worklist.pop_back_val();
		if (&MBB == &MBBBottom) {
			continue;
		}
		
		if (sectionBlocksTmp.contains(&MBB)) {
			// already seen
			continue;
		}
		//errs() << "CheapPredSectionFind ";
		//MBB.printAsOperand(errs());
		//errs() << "\n";
		if (any_of(MBB.predecessors(), [&MDT, &MBB](MachineBasicBlock * Pred) {
			return MDT.dominates(&MBB, Pred);
		})) {
			// exclude loop headers
			//errs() << "loop head\n";
			continue;
		}
		if (!MachineBasicBlock_isCheap_exceptTerminator(MBB)) {
			//errs() << "not cheap\n";
			continue;
		}
		
		sectionBlocksTmp.insert(&MBB);
		worklist.insert_range(MBB.predecessors());
	}
	// :note: sectionBlocksTmp now contains cheap transitive predecessors of  MBBBottom

	//{
	//	// transitively remove loops from 
	//	worklist.insert_range(sectionBlocksTmp);
	//	DenseSet<MachineBasicBlock *> toRm;
	//	while (!worklist.empty()) {
	//		auto &MBB = *worklist.pop_back_val();
	//		bool hasInSectionPreds = false;
	//		bool hasOutOfSectionPreds = false;
	//		for (auto *Pred : MBB.predecessors()) {
	//			if (!sectionBlocksTmp.contains(Pred) || toRm.contains(Pred)) {
	//				hasOutOfSectionPreds = true;
	//			} else {
	//				hasInSectionPreds = true;
	//			}
	//		}
	//		if (hasInSectionPreds && hasOutOfSectionPreds) {
	//			toRm.insert(&MBB);
	//			worklist.insert_range(MBB.successors());
	//		}
	//	}
	//	sectionBlocksTmp.remove_if(
	//		[&toRm](MachineBasicBlock *MBB) { return toRm.contains(MBB); });
	//}

	// filter out blocks which are just a predecessor of MBBBottom without any
	// predecessor from the section because there is no predecessor which would
	// use this block predication
	
	for (auto *MBB : sectionBlocksTmp) {
		auto isInSection = [MBB, &sectionBlocksTmp](const MachineBasicBlock *MBB0) {
			// :note: MBB0 != MBB  to prevent self loop blocks from beeig recognized as predication candidates
			return MBB0 != MBB && sectionBlocksTmp.contains(const_cast<MachineBasicBlock *>(MBB0));
		};
		auto isNotInSection = [&MBBBottom,
							   &sectionBlocksTmp](const MachineBasicBlock *MBB0) {
			return MBB0 != &MBBBottom &&
				   sectionBlocksTmp.contains(const_cast<MachineBasicBlock *>(MBB0));
		};
		if (any_of(MBB->predecessors(), isInSection) ||
			any_of(MBB->successors(), isInSection)) {
			sectionBlocks.insert(MBB);
			if (any_of(MBB->successors(), isNotInSection)) {
				blocksForBrPredication.insert(MBB);
				addInSectionSuccessorsToSetTransitively(*MBB, sectionBlocks,
														blocksForPredication);
			}
		}
	}
	// collect blocks which are not part of the section but the BR_COND is still suitable for rewrite
	for (auto *MBB : sectionBlocks) {
		for (auto Pred : MBB->predecessors()) {
			if (!blocksForBrPredication.contains(Pred)) {
				auto &BBI = BBAnalysis[Pred->getNumber()];
				if (BBI.TrueBB == &MBBBottom || BBI.FalseBB == &MBBBottom) {
					blocksForBrPredication.insert(Pred);
					addInSectionSuccessorsToSetTransitively(
						*Pred, sectionBlocks, blocksForPredication);
				}
				
			}
		}
	}
	//// predicate br_cond in predicated blocks
	//for (auto *MBB : sectionBlocks) {
	//	auto &BBI = BBAnalysis[MBB->getNumber()];
	//	if (!blocksForPredication.contains(MBB))
	//		continue;
	//	if (BBI.TrueBB && BBI.FalseBB) {
	//		blocksForBrPredication.insert(MBB);			
	//	}
	//}
	
	{
		// check for the case that blocks could be potentially all predicated
		// but there would not be any BR_COND to remove
		bool hasNotLeafBrCondToMBBBottom = false;
		for (auto *MBB : blocksForBrPredication) {
			auto &BBI = BBAnalysis[MBB->getNumber()];
			auto BB0 = BBI.TrueBB;
			auto BB1 = BBI.FalseBB;
			assert(BB0 && BB1 && "Must have ");
			for (unsigned i = 0; i < 2; ++i) {
				if (BB0 == &MBBBottom && sectionBlocks.contains(BB1)) {
					hasNotLeafBrCondToMBBBottom = true;
					break;
				}
				std::swap(BB0, BB1);
			}
			if (hasNotLeafBrCondToMBBBottom)
				break;
		}
		if (!hasNotLeafBrCondToMBBBottom) {
			return false;
		}
	}

	if (blocksForBrPredication.empty()) {
		assert(blocksForPredication.empty() &&
			   "If there is no BR_COND to be predicated there can not be "
			   "any successor of BR_COND");
		return false;
	} else {
		assert(!blocksForPredication.empty() &&
			   "Blocks which have just BBBottom as successor should not "
			   "form section of interest");
	}
	// errs() << "sectionBlocks:\n";
	// for (auto *MBB : sectionBlocks) {
	// 	errs() << "    ";
	// 	MBB->printAsOperand(errs());
	// 	errs() << "\n";
	// }
	// errs() << "blocksForPredication:\n";
	// for (auto *MBB : blocksForPredication) {
	// 	errs() << "    ";
	// 	MBB->printAsOperand(errs());
	// 	errs() << "\n";
	// }
	// errs() << "blocksForBrPredication:\n";
	// for (auto *MBB : blocksForBrPredication) {
	// 	errs() << "    ";
	// 	MBB->printAsOperand(errs());
	// 	errs() << "\n";
	// }
	return true;
}

// If we remove cond branch to BBBottom, and predicate CFG path to BBBottom instead
// we make all liveouts of predecessor a liveout of all successors on predicated path,
// this function collect such liveout registers for each block of the section.
void collectOutOfSectionNewLiveouts(
	HwtHlsVRegLiveins &VRegLiveins,
	const VRegIfConverter::MBBlockSet &sectionBlocks,
	std::unordered_map<MachineBasicBlock *, std::set<Register>> &outOfSectionLiveouts) {
	SetVector<MachineBasicBlock *> Worklist(sectionBlocks.begin(),
											sectionBlocks.end());
	while (!Worklist.empty()) {
		auto *MBB = Worklist.pop_back_val();
		if (outOfSectionLiveouts.contains(MBB))
			continue; // already resolved
		if (!all_of(MBB->predecessors(),
					[&sectionBlocks,
					 &outOfSectionLiveouts](MachineBasicBlock *Pred) {
						return !sectionBlocks.contains(Pred) ||
							   outOfSectionLiveouts.contains(Pred);
					})) {
			// if not all predecessor resolved wait until they are
			continue;
		}
		auto &MBBLiveouts = outOfSectionLiveouts[MBB];
		for (auto Pred : MBB->predecessors()) {
			if (!sectionBlocks.contains(Pred))
				continue;
			auto &PredLiveouts = outOfSectionLiveouts[Pred];
			// :note: this holds only registers which are transitive liveouts
			// from the section
			//       == not all liveouts of the block and some new liveouts may
			//       not be originally liveout or even a livein of the block
			MBBLiveouts.insert_range(PredLiveouts);
		}
		for (auto Suc : MBB->successors()) {
			if (sectionBlocks.contains(Suc)) {
				Worklist.insert(Suc);
				continue;
			}
			MBBLiveouts.insert_range(VRegLiveins.liveins(*Suc));
		}
	}
	assert(outOfSectionLiveouts.size() == sectionBlocks.size() &&
		   "Assert that all blocks were processed, this does not expect loops "
		   "and cycles, irreducible CFG");
}

void VRegIfConverter::rewriteNonLeafCondBranchToBottom_to_predicationOfSuccessors(
	MachineDomTreeUpdater &MDTU, 
	MachineBasicBlock &MBBBottom, MBBlockSet &sectionBlocks,
	MBBlockSet &blocksForPredication, MBBlockSet &blocksForBrPredication) {
	// VRegLiveins->dump();
	auto &MF = *MBBBottom.getParent();
	auto &Ctx = MF.getFunction().getContext();
	// 1 if normal execution should be activated, 0 if code should jump to
	// MBBBottom and ignore everything on the path
	Register CondReg = MRI->createVirtualRegister(&HwtFpga::anyregclsRegClass);
	MRI->setType(CondReg, LLT::scalar(1));

	MachineIRBuilder Builder(MF);
	// on all enter edges set Cond=1 to enable normal execution
	SmallSet<MachineBasicBlock *, 16> seenEnteringBlolocks;

	std::unordered_map<MachineBasicBlock*, std::set<Register>> outOfSectionLiveouts;
	collectOutOfSectionNewLiveouts(*VRegLiveins, sectionBlocks, outOfSectionLiveouts);

	for (auto *MBB : sectionBlocks) {
		for (auto *Pred : MBB->predecessors()) {
			if (sectionBlocks.contains(Pred))
				continue; // will receive CondReg as livein
			if (blocksForBrPredication.contains(Pred))
				continue; // will define the CondReg from branch condition

			if (seenEnteringBlolocks.insert(Pred).second) {
				// set CondReg=1 at the end of the block before section
				Builder.setInsertPt(*Pred, Pred->getFirstTerminator());
				auto MIB = Builder.buildInstr(HwtFpga::HWTFPGA_MUX);
				MIB.addDef(CondReg);
				MIB.addCImm(ConstantInt::getBool(Ctx, true));
			}
		}
	}
	SmallVector<MachineOperand, 2> Cond = {
		MachineOperand::CreateReg(CondReg, false),
		MachineOperand::CreateImm(0), // = not negated
	};

	for (auto *MBB : blocksForPredication) {
		auto liveins = VRegLiveins->liveinsMutable(*MBB);
		liveins.insert(CondReg);
		for (auto pred: MBB->predecessors()) {
			// errs() << "adding liveins into ";
			// pred->printAsOperand(errs());
			// errs() << " -> ";
			// MBB->printAsOperand(errs());
			// errs() << "\n";
			// for (auto r : liveins) {
			// 	errs() << " " << r.virtRegIndex();
			// }
			// errs() << "\n";
			auto newLiveouts = outOfSectionLiveouts[pred];
			liveins.insert_range(newLiveouts);
		}
	}

	// :note: predication is done in advance to prevent predication of tmp regs generated for branch condition updates
	for (auto *MBB : blocksForPredication) {
		// rewrite block to be activated only if CondReg == 1
		// :note:
		// * if the block is disabled it must preserve all liveouts
		//   of all potential predecessors which are using this block
		//   instead of removed original jump to MBBBottom
		// * if block is disabled the CFG jumps over disabled block
		//   until it reaches MBBBottom, this means that implies
		//   that defs from predicated predecessors are unused or they
		//   dominate uses, the case where some used def is disabled
		//   by predicate should not happen
		auto&BBI = BBAnalysis[MBB->getNumber()];
		
		Redefs.init(*TRI, *VRegLiveins);

		if (MRI->tracksLiveness()) {
		  Redefs.addLiveInsNoPristines(*MBB);
		}
		
		hwtHls::bimap<llvm::Register, llvm::Register> regsForSpeculation;
		auto Term = MBB->getFirstTerminator();
		auto regNeedsPreserving = [&outOfSectionLiveouts](
									  const HwtHlsVRegLiveins &VRegLiveins,
									  const MachineBasicBlock &MBB,
									  Register MOReg) {
			// errs() << "MOReg: " << MOReg.virtRegIndex() <<" ";
			if (predicateInstructionUsingDefRegRename_defNeedsTmpRegPredicate_sucToPred(
					VRegLiveins, MBB, MOReg)) {
				// errs() << "sucToPred\n";
				return true;
			}
			// is liveout from this block or any predecessor in section jumping
			// out of the section
			if (outOfSectionLiveouts[const_cast<MachineBasicBlock *>(&MBB)]
					.contains(MOReg)) {
				// errs() << "outOfSectionLiveouts\n";
				return true;
			}
			// errs() << "\n";
			return false;
		};
		// errs() << "predicating ";
		// MBB->printAsOperand(errs());
		// errs() << "\n";
		PredicateBlock(BBI, Term, Cond, regsForSpeculation, nullptr, regNeedsPreserving);
		Builder.setInsertPt(*MBB, Term);
		if (!regsForSpeculation.empty()) {
			createSpeculationMergeMuxes(*MBB, Term, regsForSpeculation, Cond, *MRI);
		}
		// handle MBBBottom predecessors which are leaf of the section
		// the BR_COND is not rerouted but the condition must be anded wih CondReg
		if (!blocksForBrPredication.contains(MBB)) {
			if (BBI.TrueBB && BBI.FalseBB) {
				DebugLoc dl = Builder.getDebugLoc();
				if (BBI.TrueBB == &MBBBottom && BBI.FalseBB == &MBBBottom) {
					TII->removeBranch(*MBB);
					TII->insertUnconditionalBranch(*MBB, &MBBBottom, dl);
					continue;
				} else if (BBI.TrueBB == &MBBBottom) {
					// swap so if the CondReg=0 the cfg jumps to predicated successor
					Condition_not(BBI.BrCond);
					std::swap(BBI.TrueBB, BBI.FalseBB);	
				}
				Condition_and(TRI, Builder, Cond, BBI.BrCond);
				TII->removeBranch(*MBB);
				TII->insertBranch(*MBB, BBI.TrueBB, BBI.FalseBB, BBI.BrCond, dl);
			}
		}
	}
	
	using DTUpdateKind = MachineDominatorTree::UpdateKind;
	SmallVector<MachineDomTreeUpdater::UpdateT> MDTUpdates;
	for (auto *MBB : blocksForBrPredication) {
		// discard BR_COND and set CondReg instead
		// or update BR_COND condition to continue in section if MBB is disabled
		auto&BBI = BBAnalysis[MBB->getNumber()];
		assert(BBI.BB == MBB);
		assert(BBI.BrCond.size() == 2);

		Builder.setInsertPt(*MBB, MBB->getFirstTerminator());
		DebugLoc dl = Builder.getDebugLoc();
		// remove BR_COND to MBBBottom and set CondReg for to disable successor instead 
		// this should be called only for blocks inside of section which
		// have some other section block and MBBBottom as a succcessor
		assert(BBI.TrueBB); 
		assert(BBI.FalseBB);
		// if the block is disabled and some of the successors is not in section
		// the condition must be modified so the code continues in the section
		// if block is disabled by CondReg=0
		
		// errs() << "rewriteNonLeafCondBranchToBottom_to_predicationOfSuccessors ";
		// MBB->printAsOperand(errs());
		// errs() << "\n";
		MachineBasicBlock * newSuc = nullptr;
		bool needsAndWithCondReg = sectionBlocks.contains(MBB);
		if (BBI.TrueBB == &MBBBottom) {
			newSuc = BBI.FalseBB;
		} else if (BBI.FalseBB == &MBBBottom) {
			newSuc = BBI.TrueBB;
		} else if (sectionBlocks.contains(BBI.TrueBB) && sectionBlocks.contains(BBI.FalseBB)) {
			// and jump with predicate to assert it to be deterministic as original
			// condition may not be computed (is set to undef)
			assert(needsAndWithCondReg);
			auto TPredicated = blocksForPredication.contains(BBI.TrueBB);
			auto FPredicated = blocksForPredication.contains(BBI.FalseBB);
						
			if (TPredicated && !FPredicated) {
				// swap so if the CondReg=0 the cfg jumps to predicated successor
				Condition_not(BBI.BrCond);
				std::swap(BBI.TrueBB, BBI.FalseBB);	
			}
			Condition_and(TRI, Builder, Cond, BBI.BrCond);
			TII->removeBranch(*MBB);
			TII->insertBranch(*MBB, BBI.TrueBB, BBI.FalseBB, BBI.BrCond, dl);
			continue;
		}
		//SmallVector<MachineOperand, 2> ContinueInSectionCond = {
		//	MachineOperand::CreateReg(CondReg, false),
		//	MachineOperand::CreateImm(0), // = not negated
		//};
		auto isJumpOutOfSection = [&MBBBottom, &sectionBlocks](MachineBasicBlock * Suc) {
			return Suc == &MBBBottom || !sectionBlocks.contains(Suc);
		};
		// update conditions so CFG continues in section if the block is disabled
		if (isJumpOutOfSection(BBI.FalseBB)) {
			reverseBranchCondition(BBI);
			assert(!isJumpOutOfSection(BBI.FalseBB));
			Builder.setInsertPt(*MBB, MBB->getFirstTerminator());
		}
		// jump to false if this block is disabled
		// BrCond &&= Cond
		llvm::SmallVector<llvm::MachineOperand, 4> OrigBrCond = BBI.BrCond;
		if (needsAndWithCondReg)
			Condition_and(TRI, Builder, Cond, BBI.BrCond);
		
		if (newSuc) {
			// replace BR_COND with just BR + predication of successors
			// set CondReg to enable or disable successors based on if original
			// jump jumped into our outside of the section
			Condition_not(OrigBrCond);
			auto sucEn =
				Condition_materializeMO(TRI, Builder, OrigBrCond);
			if (needsAndWithCondReg) {
				Builder.buildInstr(HwtFpga::G_AND, {CondReg}, {sucEn, CondReg});
			} else {
				Builder.buildInstr(HwtFpga::HWTFPGA_MUX, {CondReg}, {sucEn});
			}
			TII->removeBranch(*MBB);
			TII->insertUnconditionalBranch(*MBB, newSuc, dl);
			MBB->removeSuccessor(&MBBBottom);
			MDTUpdates.push_back({DTUpdateKind::Delete, MBB, &MBBBottom});
		} else {
			// keep BR_COND but modify cond so the CFG continues in section if the block is disabled
			TII->removeBranch(*MBB);
			TII->insertBranch(*MBB, BBI.TrueBB, BBI.FalseBB, BBI.BrCond, dl);
		}
	}

	for (auto *MBB : sectionBlocks) {
		InvalidatePreds(*MBB);
		InvalidateSuccs(*MBB);	
	}
	VRegLiveins->recompute(); // [fixme] this should not be required and VRegLiveins should be updated by this code
	InvalidatePreds(MBBBottom);
	InvalidateSuccs(MBBBottom);	
	MDTU.applyUpdates(MDTUpdates);
}

bool VRegIfConverter::tryCheapPredSectionBrCondPruning(
	llvm::MachineFunction &MF, llvm::MachineDomTreeUpdater &MDTU,
	llvm ::Statistic &numCntr) {
	bool Change = false;
	for (auto &MBB : MF) {
		auto &BBI = BBAnalysis[MBB.getNumber()];
		if (!BBI.IsBrAnalyzable)
			continue;
		if (BBI.BB->pred_size() < 2)
			continue;

			
		MBBlockSet sectionBlocks;
		MBBlockSet blocksForPredication;
		MBBlockSet blocksForBrPredication;
		if (!CheapPredSectionFind(MDTU.getDomTree(), MBB, sectionBlocks,
								  blocksForPredication,
								  blocksForBrPredication)) {
			continue;
		}
		
		auto KindName = IfcvtKind_toStr(IfcvtKind::ICCheapPredSectionBrCondPruning);
		if (enableTrace)
		  hwtHls::writeCFGToDotFile(MF, std::string("IC.") + std::to_string(dbgCntr++) + KindName +  + "-before.dot");
		rewriteNonLeafCondBranchToBottom_to_predicationOfSuccessors(
			MDTU, MBB, sectionBlocks, blocksForPredication,
			blocksForBrPredication);
		if (enableTrace)
		  hwtHls::writeCFGToDotFile(MF, std::string("IC.") + std::to_string(dbgCntr++) + KindName +  + "-after.dot");
		++numCntr;
		Change = true;
		onChangeTestCallback("CheapPredSectionBrCondPruning", MF);
		// because we want to prioritize other rules first as this
	   // has higher overhead
		break;
	}

	return Change;
}

}