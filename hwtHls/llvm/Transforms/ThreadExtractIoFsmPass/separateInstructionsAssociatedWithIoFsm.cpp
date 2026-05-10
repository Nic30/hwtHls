#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/separateInstructionsAssociatedWithIoFsm.h>
#include <hwtHls/llvm/Transforms/ThreadExtractIoFsmPass/constructCommunicationBetweenOriginalAndExtractedLoop.h>
#include <llvm/Analysis/CFG.h>
#include <llvm/Analysis/LoopIterator.h>

#include <stdexcept>

// :note: DEBUG_TYPE must be defined before InstructionWorklist include
#define DEBUG_TYPE "thread-extract-iofsm"

#include <llvm/Transforms/Utils/InstructionWorklist.h>

using namespace llvm;

namespace hwtHls {

/*
 * :param reachedLoops: loops which are outside or inside of this loop which were
 *        reached when searching from block BB in def->use direction
 * */
void getSectionUntilNextLoopOrBackedge(LoopInfo &LI, Loop *curLoop,
		BasicBlock *BB, SetVector<BasicBlock*> &collectedBlocks,
		SetVector<Loop*> &reachedLoops) {
	if (collectedBlocks.contains(BB))
		return;
	auto L = LI.getLoopFor(BB);
	if (L != curLoop) {
		reachedLoops.insert(L);
	} else {
		collectedBlocks.insert(BB);
		for (BasicBlock *suc : successors(BB)) {
			if (L && L->getHeader() == suc)
				continue; // skip backedges
			getSectionUntilNextLoopOrBackedge(LI, curLoop, suc, collectedBlocks,
					reachedLoops);
		}
	}
}

void findLoopSections(LoopInfo &LI, Function &F, Loop *L,
		std::map<Loop*, LoopExports> &loopExports) {
	SetVector<BasicBlock*> sectionBlocks;
	SetVector<Loop*> reachedChildOrSiblingLoops;
	if (L) {
		LoopBlocksRPO RPOT(L);
		RPOT.perform(&LI);
		if (containsIrreducibleCFG<const BasicBlock*>(RPOT, LI))
			throw std::runtime_error(
					"ThreadExtractIoFsmPass: can not rewrite loop with irreducible CFG");
		assert(!loopExports.contains(L));
		loopExports[L] = { };
		if (L->getSubLoops().empty()) {
			auto bodyBlocks = L->getBlocks();
			LoopExports &loopExport = loopExports[L];
			loopExport.beforeExitOrLatchSection.insert(bodyBlocks.begin(),
					bodyBlocks.end());
			return;
		} else {
			// find section between header and header of child loops
			getSectionUntilNextLoopOrBackedge(LI, L, L->getHeader(),
					sectionBlocks, reachedChildOrSiblingLoops);
		}
	} else {
		// the top of the function
		getSectionUntilNextLoopOrBackedge(LI, nullptr, &F.getEntryBlock(),
				sectionBlocks, reachedChildOrSiblingLoops);
		// assume that if there is a top loop it is an infinite loop
	}

	// find section after child loop and possibly other child loop header or backedge
	assert(!reachedChildOrSiblingLoops.contains(L));
	assert(reachedChildOrSiblingLoops.size()); // because the loop has sub loops they have to be reachable from header
	if (reachedChildOrSiblingLoops.size() > 1)
		llvm_unreachable(
				"NotImplemented loop with multiple child loops which not clear dominance");
	for (;;) {
		SmallVector<BasicBlock*> exitBlocks;
		for (auto subL : reachedChildOrSiblingLoops) {
			if (loopExports.find(subL) != loopExports.end()) {
				continue; // subL is some parent loop, skip it because it is currently processed in recursive call of this fn
			}
			findLoopSections(LI, F, subL, loopExports);
			LoopExports &subLoopExport = loopExports[subL];
			subLoopExport.beforeHeaderSection.insert(sectionBlocks.begin(),
					sectionBlocks.end());

			// for successor child loops collect the new header section and findLoopSections also for them recursively
			// until we reach before exit or latch section of this loop
			subL->getExitBlocks(exitBlocks);
			// :note: expects formDedicatedUniqueLoopExitingAndLatchBB to be applied
		}
		sectionBlocks.clear();
		reachedChildOrSiblingLoops.clear();
		for (auto BB : exitBlocks) {
			getSectionUntilNextLoopOrBackedge(LI, L, BB, sectionBlocks,
					reachedChildOrSiblingLoops);
		}
		if (reachedChildOrSiblingLoops.empty()) {
			LoopExports &subLoopExport = loopExports[L];
			subLoopExport.beforeExitOrLatchSection.insert(sectionBlocks.begin(),
					sectionBlocks.end());
			break;
		}

	}

}
//// discover the blocks between:
//// * entry and the first loop
//// * or loop header and header of next loop or backedge
//// * or after loop until next loop or backedge
//void collectInstructionsDefinedInOldAndUsedInNewFn(Function &F, LoopInfo &LI,
//		DominatorTree &DT, ValueToValueMapTy &VMap, ValueToValueMapTy &VMapRev,
//		const SetVector<Value*> &newFnSpecificVal,
//		std::map<Loop*, LoopExports> &loopExports) {
//
//	for (Loop *L : LI.getLoopsInPreorder()) {
//		// iter top first, child in code order
//		loopExports[L] = { };
//		auto &loopExport = loopExports[L];
//		errs() << "L: " << *L;
//		for (auto *BB : L->blocks()) {
//			errs() << "   bb:" << BB->getName() << "   " << *LI.getLoopFor(BB)
//					<< "\n";
//		}
//		// :note: loop->blocks() returns all blocks int his loop, including blocks which are possibly in some child loop
//		for (auto *BB : L->blocks()) {
//			BasicBlock *newBB = dyn_cast<BasicBlock>(&*VMap[BB]);
//			for (auto &newI : *newBB) {
//				for (auto *op : newI.operand_values()) {
//					auto opI = dyn_cast<Instruction>(op);
//					if (!opI)
//						continue;
//					if (newFnSpecificVal.contains(opI))
//						continue;
//
//					auto *oldOpI = dyn_cast<Instruction>(&*VMapRev[opI]);
//					if (L->contains(oldOpI)) {
//						// dependency defined in the loop so it should be copied to extracted thread at the end
//						loopExport.beforeExit.insert(oldOpI);
//					} else {
//						// dependency defined before the loop so it should be copied before begin of this loop
//						loopExport.beforeHeader.insert(oldOpI);
//					}
//				}
//			}
//		}
//	}
//}

void detectExtractedCodeAndRemoveItFromOldFn(llvm::Argument &Arg, Function &F,
		ValueToValueMapTy &VMap, SetVector<Value*> &newFnSpecificValInNewFn,
		SetVector<Instruction*> &instrSpecificToThisArgInOldFn) {

	InstructionWorklist Worklist;
	auto addAllOperandsToWorklist = [&Worklist, &Arg](Instruction &I) {
		for (auto *op : I.operand_values()) {
			if (auto opA = dyn_cast<Argument>(op)) {
				if (opA != &Arg)
					return; // this instructions works with some other argument so it is not
				// private to IO FSM of Arg
			}
		}
		for (auto *op : I.operand_values()) {
			if (auto opI = dyn_cast<Instruction>(op)) {
				Worklist.push(opI);
			}
		}
	};
	//SetVector<BasicBlock*> originalBlockWithExtractedIo;
	bool initWorklist = true;
	for (;;) {
		SetVector<Instruction*> instrSpecificToThisArgInOldFnTmp;
		if (initWorklist) {
			// initialize worklist
			for (User *U : Arg.users()) {
				if (auto I = dyn_cast<Instruction>(U)) {
					if (isa<LoadInst>(I)) {
						throw std::runtime_error("ThreadExtractorIoFsmPass/detectExtractedCodeAndRemoveItFromOldFn for input");
					} else if (isa<StoreInst>(I)) {
						//originalBlockWithExtractedIo.insert(I->getParent());
						instrSpecificToThisArgInOldFnTmp.insert(I);
						addAllOperandsToWorklist(*I);
					}
				}
			}
			initWorklist = false;
		}
		// find instruction specific to this IO Argument
		while (!Worklist.isEmpty()) {
			// Walk deferred instructions in reverse order, and push them to the
			// worklist, which means they'll end up popped from the worklist in-order.
			while (llvm::Instruction *I = Worklist.popDeferred()) {
				Worklist.push(I);
			}

			llvm::Instruction *I = Worklist.removeOne();
			if (instrSpecificToThisArgInOldFnTmp.contains(I))
				continue; // already selected
			bool hasSomeOtherIoArgAsOperand = false;
			for (Use &op : I->operands()) {
				auto opA = dyn_cast<Argument>(op.get());
				if (opA && opA != &Arg) {
					hasSomeOtherIoArgAsOperand = true;
					break;
				}
			}
			if (!hasSomeOtherIoArgAsOperand) {
				bool allUsersAreSelected = true;
				for (User *u : I->users()) {
					if (auto ui = dyn_cast<Instruction>(u)) {
						if (!instrSpecificToThisArgInOldFn.contains(ui)
								&& !instrSpecificToThisArgInOldFnTmp.contains(
										ui)) {
							allUsersAreSelected = false;
							break;
						}
					}
				}
				if (allUsersAreSelected) {
					instrSpecificToThisArgInOldFnTmp.insert(I);
					addAllOperandsToWorklist(*I);
				}
			}
		}
		instrSpecificToThisArgInOldFn.insert(
				instrSpecificToThisArgInOldFnTmp.begin(),
				instrSpecificToThisArgInOldFnTmp.end());
		if (instrSpecificToThisArgInOldFnTmp.empty())
			break; // no additional instruction specific to this IO Argument were found

		// remove selected code from original function
		for (auto *I : instrSpecificToThisArgInOldFnTmp) {
			// errs() << "erasing from old: " << *I << "\n";
			Value &newI = *VMap[I];
			newFnSpecificValInNewFn.insert(&newI);
			// required because erase order does not obey use->def order
			I->replaceAllUsesWith(PoisonValue::get(I->getType()));
			I->eraseFromParent();
		}
		// try to simplify CFG so we can remove branch conditions if possible
		// [todo]
	}
	Worklist.zap();
}

/*
 * Iterate instructions in function F, if the instruction is not selected
 * and it is not terminator, assert that it is not used by any selected instruction or terminal and erase it from parent
 * */
void removeNonSelectedInstructionsFromFunctionIfNotTerminal(llvm::Function &F,
		const SetVector<llvm::Value*> &selectedInstructions) {
	for (auto &BB : F) {
		// Use make_early_inc_range to safely remove instructions during iteration
		for (auto &I : make_early_inc_range(BB)) {
			if (selectedInstructions.contains(&I)) {
				continue; // is selected thus non removable
			}
			if (I.isTerminator())
				continue;

			// Check if the instruction is used by any selected instruction or terminal
			for (auto *U : I.users()) {
				Instruction *userInst = dyn_cast<Instruction>(U);
				if (!userInst || selectedInstructions.contains(userInst)) {
					errs() << "I:" << I << "\nuser:" << *userInst << "\n";
					llvm_unreachable(
							"The instruction should be removed, yet it still have some use, which should have been already updated");
				}
			}

			// If the instruction is not used by any selected instruction or terminal, remove it
			// required because erase order does not obey use->def order
			I.replaceAllUsesWith(PoisonValue::get(I.getType()));
			I.eraseFromParent();
		}
	}
}

void separateInstructionsAssociatedWithIoFsm(IRBuilder<> &Builder,
		llvm::Argument &Arg, Function &F, Function &extractedF,
		ValueToValueMapTy &VMap, DomTreeUpdater &DTU, LoopInfo &LI,
		SmallVector<ArgToAddToParentFn> &argsToAddToOldFn,
		SmallVector<ArgToAddToParentFn> &argsToAddToNewFn) {

	ValueToValueMapTy VMapRev;
	for (const auto &V : VMap) {
		VMapRev.insert(
				{ const_cast<Value*>(&*V.second), const_cast<Value*>(V.first) });
	}

	SetVector<Value*> newFnSpecificValInNewFn;
	SetVector<Instruction*> instrSpecificToThisArgInOldFn;
	detectExtractedCodeAndRemoveItFromOldFn(Arg, F, VMap,
			newFnSpecificValInNewFn, instrSpecificToThisArgInOldFn);

	// for each loop, resolve which values are required to transfer from original to new function
	// Iter loops in the order the child first and the later loop first.
	// for each loop collect all instructions which are used in extracted code but defined in original
	std::map<Loop*, LoopExports> loopExports;
	// collectInstructionsDefinedInOldAndUsedInNewFn(F, LI, DTU.getDomTree(), VMap,
	// 		VMapRev, newFnSpecificValInNewFn, loopExports);
	findLoopSections(LI, F, nullptr, loopExports);
	//for (std::pair<Loop* const, LoopExports> &item : loopExports) {
	//	if (item.first)
	//		errs() << *item.first << ":\n";
	//	else
	//		errs() << "top:\n";
	//	errs() << " beforeHeaderSection:\n";
	//	for (auto *BB : item.second.beforeHeaderSection) {
	//		errs() << "    " << BB->getName() << "\n";
	//	}
	//	errs() << " beforeExitOrLatchSection:\n";
	//	for (auto *BB : item.second.beforeExitOrLatchSection) {
	//		errs() << "    " << BB->getName() << "\n";
	//	}
	//	errs() << "\n";
	//}
	//errs() << "constructCommunicationBetweenOriginalAndExtractedLoop\n";
	for (Loop *L : LI.getTopLevelLoops()) {
		resolveExportedValues(LI, L, VMap, VMapRev, newFnSpecificValInNewFn,
				loopExports);
	}

	SetVector<Instruction*> alreadyExported;
	// construct tmp alloca and create a store to it in original function and load from it in new function
	auto allocaInsertPointInOld = F.getEntryBlock().begin();
	auto allocaInsertPointInNew = extractedF.getEntryBlock().begin();
	if (DTU.hasPendingUpdates())
		DTU.flush();
	for (Loop *L : LI.getTopLevelLoops()) {
		// iter parent first then children
		constructCommunicationBetweenOriginalAndExtractedLoop(Builder, F, DTU.getDomTree(),
				extractedF, argsToAddToOldFn, argsToAddToNewFn, loopExports,
				alreadyExported, VMap, VMapRev, allocaInsertPointInOld,
				allocaInsertPointInNew, L, newFnSpecificValInNewFn);
	}
	// after extracted code in extractedF was updated to use values exported from F
	// delete all code from extractedF which was not extracted and is not terminator
	removeNonSelectedInstructionsFromFunctionIfNotTerminal(extractedF,
			newFnSpecificValInNewFn);
	// for an extracted region of code there are two complications
	// * we would like to extract most of the branching private to IoFsm
	//   but the branches are rarely private to extracted region
	// * If we copy all branches and related instructions we potentially duplicate large amount of code
	//   If we do not copy it, we would not be able to analyze cfg later as the branch conditions
	//   will be computed in original code and CFG analysis would not be able to analyze them

	// if the loop contains only access to this io Arg then the loop will be inside of extracted IoFsm function
	// if it contains also some other IO there will be channel which transfers data on each iteration
	// to synchronize code between original and extracted IoFsm
	// * if extracted IoFsm is for output, then the data is transferred between original latch and new header
	//
}

}
