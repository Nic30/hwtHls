#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass_aggresiveStoreSink.h>
#include <algorithm>

#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/Analysis/IteratedDominanceFrontier.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

#define DEBUG_TYPE "simplifycfg2"
using namespace llvm;

namespace hwtHls {

bool _findOneEntryOneExitBlockSubraph(DominatorTree &DT, BasicBlock &BBStart,
		BasicBlock &cur, SmallVector<BasicBlock*> &foundBlocks) {
	for (BasicBlock *pred : predecessors(&cur)) {
		if (std::find(foundBlocks.begin(), foundBlocks.end(), pred)
				!= foundBlocks.end())
			continue; // skip already seen
		else if (!DT.dominates(&BBStart, pred)) {
			// if any block reached is not dominated by BBstart it means that that the selected block group
			// has another entry point than BBStart
			return false;
		} else if (pred != &BBStart) {
			foundBlocks.push_back(pred);
			_findOneEntryOneExitBlockSubraph(DT, BBStart, *pred, foundBlocks);
		}
	}
	return true;
}

bool findOneEntryOneExitBlockSubraph(DominatorTree &DT, BasicBlock &BBStart,
		BasicBlock &BBEnd, SmallVector<BasicBlock*> &foundBlocks) {
	// start from end and continue upwards until start is reached,
	foundBlocks.push_back(&BBStart);
	if (&BBStart == &BBEnd) {
		return true;
	}
	foundBlocks.push_back(&BBEnd);
	if (!_findOneEntryOneExitBlockSubraph(DT, BBStart, BBEnd, foundBlocks))
		return false;

	// if any block has a successor which was not reached and is not BBend it means that the selected block group
	// has another exit than BBEnd
	for (auto *BB : foundBlocks) {
		if (BB == &BBEnd) {
			continue;
		}
		for (BasicBlock *suc : successors(BB)) {
			if (std::find(foundBlocks.begin(), foundBlocks.end(), suc)
					== foundBlocks.end()) {
				return false;
			}
		}
	}
	return true;
}

// check if every def in candidate blocks is not used in BBEnd or after
bool checkIfDefsUsedOnlyLocally(SmallVector<BasicBlock*> &foundBlocks,
		llvm::BasicBlock &BBStart, llvm::BasicBlock *BBEnd) {
	for (BasicBlock *BB : foundBlocks) {
		if (BB == &BBStart || BB == BBEnd)
			continue;

		for (Instruction &I : *BB) {
			for (const Use &u : I.uses()) {
				if (Instruction *UI = cast<Instruction>(u.getUser())) {
					auto P = UI->getParent();
					if (P == &BBStart || P == BBEnd
							|| std::find(foundBlocks.begin(), foundBlocks.end(),
									P) == foundBlocks.end()) {
						return false;
					}
				}
			}
		}
	}
	return true;
}

// use BBStart branch condition to split BBEnd predecessors to two groups (not necessary exclusive)
bool checkBBEndPHIsDrivenByBBStartCond(DominatorTree &DT,
		llvm::BasicBlock &BBStart, llvm::BasicBlock *BBEnd,
		SetVector<BasicBlock*> &BBStartTBBEndPredecs,
		SetVector<BasicBlock*> &BBStartFBBEndPredecs) {
	auto *BR0 = dyn_cast<BranchInst>(BBStart.getTerminator());
	assert(BR0 && BR0->isConditional());
	auto *TBB = BR0->getSuccessor(0);
	auto *FBB = BR0->getSuccessor(1);
	// cycle on BBStart is not supported
	if (TBB == &BBStart)
		return false;
	else if (TBB == BBEnd)
		BBStartTBBEndPredecs.insert(&BBStart);
	if (FBB == &BBStart)
		return false;
	else if (FBB == BBEnd)
		BBStartFBBEndPredecs.insert(&BBStart);

	for (BasicBlock *pred : predecessors(BBEnd)) {
		if (TBB != BBEnd) {
			if (DT.dominates(TBB, pred)) {
				BBStartTBBEndPredecs.insert(pred);
			}
		}
		if (FBB != BBEnd) {
			if (DT.dominates(FBB, pred)) {
				BBStartFBBEndPredecs.insert(pred);
			}
		}
	}
	return true;
}

void updatePhisInBBEndSuccessor(
		const SetVector<BasicBlock*> &BBEndPredecsForThisBranch,
		llvm::BasicBlock *BBEndSuc, llvm::BasicBlock *BBEnd) {
	// update PHIs in original end successors
	for (PHINode &phi : BBEndSuc->phis()) {
		// :attention: previously when searching or BBStartTBBEndPredecs we checked that the value is same for all blocks
		if (BBEndPredecsForThisBranch.size()) {
			phi.replaceIncomingBlockWith(BBEnd, BBEndPredecsForThisBranch[0]);
			if (BBEndPredecsForThisBranch.size() > 1) {
				// now there are more predecessors copy the value for each one
				auto V = phi.getIncomingValueForBlock(
						BBEndPredecsForThisBranch[0]);
				bool first = true;
				for (auto predBB : BBEndPredecsForThisBranch) {
					if (first) {
						first = false;
						continue;
					}
					phi.addIncoming(V, predBB);
				}
			}
		}
	}
}

void overwriteBBEndSuccessor(DomTreeUpdater &DTU, llvm::BranchInst *BBEndBr,
		size_t sucIndex, BasicBlock &BBStart, llvm::BasicBlock *BBStartT) {
	auto BBEnd = BBEndBr->getParent();
	if (BBStartT == BBEnd)
		return; // no update because there is no block between start and end
	DTU.applyUpdates(
			{ { DominatorTree::Delete, BBEnd, BBEndBr->getSuccessor(sucIndex) } });
	BBEndBr->setSuccessor(sucIndex, BBStartT);
	DTU.applyUpdates( { { DominatorTree::Insert, BBEnd, BBStartT } });
	// update phis in moved blocks
	for (PHINode &phi : BBStartT->phis()) {
		phi.replaceIncomingBlockWith(&BBStart, BBEnd);
	}
}

void replaceSuccessorWith(const SetVector<BasicBlock*> &blocks,
		DomTreeUpdater &DTU, llvm::BasicBlock *curSuc,
		llvm::BasicBlock *newSuc) {
	for (BasicBlock *BB : blocks) {
		DTU.applyUpdates( { { DominatorTree::Delete, BB, curSuc } });
		BB->getTerminator()->replaceSuccessorWith(curSuc, newSuc);
		DTU.applyUpdates( { { DominatorTree::Delete, BB, newSuc } });
	}
}

bool tryToMoveBlocksBehindBBEnd(SmallVector<BasicBlock*> &foundBlocks,
		llvm::BasicBlock &BBStart, llvm::BasicBlock *BBEnd, DomTreeUpdater &DTU,
		DominatorTree &DT, llvm::BranchInst *BR0) {
	// check if every def in candidate blocks is not used in BBEnd or after
	bool canMoveAsAWhole = checkIfDefsUsedOnlyLocally(foundBlocks, BBStart,
			BBEnd);
	if (!canMoveAsAWhole)
		return false;
	if (BBEnd->phis().begin() != BBEnd->phis().end()) {
		// find direct predecessors of BBEnd on each branch from BBStart separately
		SetVector<BasicBlock*> BBStartTBBEndPredecs;
		SetVector<BasicBlock*> BBStartFBBEndPredecs;
		if (checkBBEndPHIsDrivenByBBStartCond(DT, BBStart, BBEnd,
				BBStartTBBEndPredecs, BBStartFBBEndPredecs)) {
			// check if it is possible to update PHIs in BBEnd
			SmallVector<std::pair<Value*, Value*> > phiUpdates;
			for (PHINode &phi : BBEnd->phis()) {
				Value *TVal = nullptr;
				Value *FVal = nullptr;
				for (auto *pred : phi.blocks()) {
					if (pred == BBEnd) {
						// [todo] mark that phi should be kept, but replace all other predecessor blocks with BBStart with newly generated value by select
						throw std::runtime_error("NotImplemented");
					}
					auto V = phi.getIncomingValueForBlock(pred);
					if (BR0->getSuccessor(0) == BBEnd
							|| BBStartTBBEndPredecs.count(pred)) {
						if (TVal == nullptr) {
							TVal = V;
						} else if (TVal != V) {
							return false;
						}
					} else {
						assert(BBStartFBBEndPredecs.count(pred));
						if (FVal == nullptr) {
							FVal = V;
						} else if (TVal != V) {
							return false;
						}
					}
				}
				phiUpdates.push_back( { TVal, FVal });
			}
			// all PHIs can be rewritten as a select

			// replace BBEnd PHIs with select in BBStart
			IRBuilder<> Builder(BBStart.getTerminator());
			auto *BBStartBr = dyn_cast<BranchInst>(BBStart.getTerminator());
			Value *C = BBStartBr->getCondition();
			auto phiUpdtIt = phiUpdates.begin();
			for (PHINode &phi : make_early_inc_range(BBEnd->phis())) {
				auto *phiReplacement = Builder.CreateSelect(C, phiUpdtIt->first,
						phiUpdtIt->second, phi.getName());
				phi.replaceAllUsesWith(phiReplacement);
				phi.eraseFromParent();
			}

			// set BBStartT as BBEndT (and same for F branch) (we must insert between, not replace, because BBEndT may have other predecessors)
			auto *BBEndBr = dyn_cast<BranchInst>(BBEnd->getTerminator());
			auto *BBStartT = BBStartBr->getSuccessor(0);
			auto *BBStartF = BBStartBr->getSuccessor(1);
			auto *BBEndT = BBEndBr->getSuccessor(0);
			auto *BBEndF = BBEndBr->getSuccessor(1);

			// move BBStart successors as BBEnd successors
			overwriteBBEndSuccessor(DTU, BBEndBr, 0, BBStart, BBStartT);
			overwriteBBEndSuccessor(DTU, BBEndBr, 1, BBStart, BBStartF);
			// update terminators in moved blocks to continue to BBEnd successors
			// for bb in BBStartTBBEndPredecs replace BBEnd with BBEndT (and same for F branch)
			replaceSuccessorWith(BBStartTBBEndPredecs, DTU, BBEnd, BBEndT);
			replaceSuccessorWith(BBStartFBBEndPredecs, DTU, BBEnd, BBEndF);

			// replace branch from BBStart to an unconditional branch to BBEnd
			for (BasicBlock *suc : BBStartBr->successors()) {
				DTU.applyUpdates( { { DominatorTree::Delete, &BBStart, suc } });
			}
			BBStartBr->eraseFromParent();
			Builder.SetInsertPoint(&BBStart);
			Builder.CreateBr(BBEnd);
			DTU.applyUpdates( { { DominatorTree::Insert, &BBStart, BBEnd }, });

			// merge trivial branches
			MergeBlockIntoPredecessor(BBEnd, &DTU);
			DTU.flush();

			// std::string errTmp =
			// 		"hwtHls::tryToMoveBlocksBehindBBEnd corrupted function ";
			// llvm::raw_string_ostream errSS(errTmp);
			// auto &F =* BBStart.getParent();
			// errSS << F.getName().str();
			// errSS << "\n";
			// if (verifyModule(*F.getParent(), &errSS)) {
			// 	throw std::runtime_error(errSS.str());
			// }
			// if (!DT.verify()) {
			// 	throw std::runtime_error("hwtHls::tryToMoveBlocksBehindBBEnd corrupted DominatorTree");
			// }
			return true;
		}
	}
	return false;
}

bool BasicBlock_containsMem(llvm::BasicBlock *BB) {
	for (Instruction &I : *BB) {
		if (I.mayReadOrWriteMemory()) {
			return true;
		}
	}
	return false;
}

bool SimplifyCFG2Pass_aggresiveStoreSink(DomTreeUpdater &DTU,
		llvm::BasicBlock &BBStart) {

	if (!DTU.hasDomTree())
		return false;
	DominatorTree &DT = DTU.getDomTree();
	if (auto *BR0 = dyn_cast<BranchInst>(BBStart.getTerminator())) {
		if (!BR0->isConditional())
			return false;
		Value *C = BR0->getCondition();
		if (DTU.hasPendingUpdates()) {
			DTU.flush();
		}
		SmallVector<BasicBlock*> descendants;
		DT.getDescendants(&BBStart, descendants);
		for (auto *BBEnd : descendants) {
			if (BBEnd == &BBStart)
				continue;
			if (auto *BREnd = dyn_cast<BranchInst>(BBEnd->getTerminator())) {
				if (!BREnd->isConditional() || BREnd->getCondition() != C) {
					continue;
				}

				SmallVector<BasicBlock*> foundBlocks;
				if (!findOneEntryOneExitBlockSubraph(DT, BBStart, *BBEnd,
						foundBlocks)) {
					continue;
				}

				if (foundBlocks.size() <= 2) {
					// nothing to move
					assert(foundBlocks.size() == 2);
					continue;
				}

				if (BasicBlock_containsMem(BBEnd)
						&& any_of(foundBlocks, BasicBlock_containsMem)) {
					// we can not reorder mem accesses
					continue;
				}

				// check if every def in candidate blocks is not used in BBEnd or after
				if (tryToMoveBlocksBehindBBEnd(foundBlocks, BBStart, BBEnd, DTU,
						DT, BR0)) {
					// if we sink whole blocks we do not have to construct any new PHIs
					return true;
				}
				// [todo] try sink at least stores

				// if we sink just some instructions we have to construct PHI in every block from original block where instruction was to BBEnd
			}
		}
	}

	return false;
}

}
