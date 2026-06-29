#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/trivialSimplifyCFGPass.h>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/CFG.h>
#include <llvm/Analysis/DomTreeUpdater.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

#include <algorithm>

#define DEBUG_TYPE "hwthls-trivialsimplifycfg"
// #define DBG_VERIFY_AFTER_EVERY_MODIFICATION
// #undef LLVM_DEBUG
// #define LLVM_DEBUG(x) x

#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
#include <llvm/IR/Verifier.h>
#endif

using namespace llvm;

namespace hwtHls {

void mergeScavengedMetadata(
		const SmallVector<std::pair<unsigned, MDNode*> > &MDs,
		Instruction *newBr) {
	for (const auto &md : MDs) {
		if (newBr->getMetadata(md.first) == md.second)
			continue;

		assert(
				!newBr->hasMetadata(md.first)
						&& "merge of metadata not implemented");
		newBr->setMetadata(md.first, md.second);
	}
}

void scavengeTerminatorMetadata(Instruction *br, Instruction *newBr) {
	SmallVector<std::pair<unsigned, MDNode*>> MDs;
	br->getAllMetadata(MDs);
	mergeScavengedMetadata(MDs, newBr);
}

static bool tryRemoveSingleSuccessorSinglePredecessorBlock(DomTreeUpdater &DTU,
		BasicBlock *BB, BasicBlock *PredBB, BasicBlock *SucBB,
		llvm::SmallSetVector<WeakVH, 16> &WorkList) {
	// Remove empty basic block if has single successor and predecessor and
	// may be replaced by predecessor in successor PHIs

	// detect if PHIs are compatible
	SmallVector<PHINode*, 4> alreadyHasTheValueInPhis;
	for (PHINode &SucPhi : SucBB->phis()) {
		auto BBVal = SucPhi.getIncomingValueForBlock(BB);
		int Idx = SucPhi.getBasicBlockIndex(PredBB);
		if (Idx >= 0) {
			// PredBB is already a predecessor of SucBB
			auto PredBBVal = SucPhi.getIncomingValue(Idx);
			if (BBVal != PredBBVal) {
				// can not replace because the block is required to select other value in successor PHI
				return false;
			} else {
				alreadyHasTheValueInPhis.push_back(&SucPhi);
			}
		}
	}
	LLVM_DEBUG(
			dbgs() << "tryRemoveSingleSuccessorSinglePredecessorBlock: "; PredBB->printAsOperand(dbgs()); dbgs() << '\n');

	// update successor PHIs
	for (PHINode &SucPhi : SucBB->phis()) {
		if (std::find(alreadyHasTheValueInPhis.begin(),
				alreadyHasTheValueInPhis.end(), &SucPhi)
				!= alreadyHasTheValueInPhis.end()) {
			// SucBB already has predBB as predecessors and the values are the same,
			// remove value for BB and keep only for SucBB
			SucPhi.removeIncomingValue(BB, false);
		}
	}

	scavengeTerminatorMetadata(BB->getTerminator(), PredBB->getTerminator());
	// guaranteed that there is only one branch with this block as a target

	// if PredBB terminator become non-conditional it must be rewritten otherwise
	// PredBB would appear twice in SuccBB predecessors
	auto PredTerm = PredBB->getTerminator();
	assert(BB != SucBB);
	PredTerm->replaceSuccessorWith(BB, SucBB);
	DTU.applyUpdates( { { DominatorTree::Delete, PredBB, BB }, //
			{ DominatorTree::Insert, PredBB, SucBB }, //
			});
	if (auto PredTermBr = dyn_cast<BranchInst>(PredTerm)) {
		if (PredTermBr->isConditional()
				&& PredTermBr->getSuccessor(0) == PredTermBr->getSuccessor(1)) {
			auto newTerm = BranchInst::Create(PredTermBr->getSuccessor(0),
					PredBB);
			scavengeTerminatorMetadata(PredTerm, newTerm);
			PredTerm->eraseFromParent();
		}
	}
	// because there is a single predecessor
	BB->replaceAllUsesWith(PredBB); // replace in other PHIs, which effectively disconnect this from predecessor
	BB->getTerminator()->replaceSuccessorWith(SucBB, BB);
	DTU.applyUpdates( { { DominatorTree::Delete, BB, SucBB }, //
			{ DominatorTree::Insert, BB, BB }, //
			});
	assert(BB->hasNPredecessors(1));
	// BB->eraseFromParent();
	DeleteDeadBlock(BB, &DTU);
	assert(PredBB->getParent());
	WorkList.insert(PredBB);
	assert(PredBB->getParent());
	WorkList.insert(SucBB);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto& F = *PredBB->getParent();
	assert(!verifyFunction(F, &errs()));
#endif
	return true;
}

bool tryRemoveSingleSuccessorManyPredecessorBlock(DomTreeUpdater &DTU,
		BasicBlock *BB, BasicBlock *SucBB,
		llvm::SmallSetVector<WeakVH, 16> &WorkList) {

	SmallVector<PHINode*, 4> alreadyHasTheValueInPhis;
	for (PHINode &SucPhi : SucBB->phis()) {
		for (auto *SucPredBB : SucPhi.blocks()) {
			auto SucPredVal = SucPhi.getIncomingValueForBlock(&*SucPredBB);
			auto isSucPredBB = [&SucPredBB](BasicBlock *otherBB) {
				return otherBB == SucPredBB;
			};
			if (any_of(predecessors(BB), isSucPredBB)) {
				Value *CurVal = SucPhi.getIncomingValueForBlock(BB);
				if (CurVal != SucPredVal) {
					// can not replace because the block is required to select other value in successor PHI
					return false;
				} else {
					alreadyHasTheValueInPhis.push_back(&SucPhi);
				}
			}
		}
	}

	LLVM_DEBUG(
			dbgs() << "tryRemoveSingleSuccessorManyPredecessorBlock: "; BB->printAsOperand(dbgs()); dbgs() << '\n');
	// update PHIs
	for (PHINode &SucPhi : SucBB->phis()) {
		if (std::find(alreadyHasTheValueInPhis.begin(),
				alreadyHasTheValueInPhis.end(), &SucPhi)
				!= alreadyHasTheValueInPhis.end())
			SucPhi.removeIncomingValue(BB, false);
	}
	std::vector<BasicBlock*> predecs;
	for (auto *OtherBB : predecessors(BB)) {
		predecs.push_back(OtherBB);
	}
	for (auto *PredBB : predecs) {
		// guaranteed that there is only one branch with this block as a target
		PredBB->getTerminator()->replaceSuccessorWith(BB, SucBB);
		DTU.applyUpdates( { { DominatorTree::Delete, PredBB, BB }, //
				{ DominatorTree::Insert, PredBB, SucBB }, //
				});

		// because there is a single predecessor
		for (auto &phi : SucBB->phis()) {
			auto idx = phi.getBasicBlockIndex(PredBB);
			auto curV = phi.getIncomingValueForBlock(BB);
			if (idx < 0) {
				phi.addIncoming(curV, PredBB);
			} else {
				assert(
						phi.getIncomingValue(idx) == curV
								&& "should already been checked that this is the case, if not the BB remove should not be executed");
			}
		}
		scavengeTerminatorMetadata(BB->getTerminator(),
				PredBB->getTerminator());
		assert(PredBB->getParent());
		WorkList.insert(PredBB);
	}
	for (auto &phi : SucBB->phis()) {
		phi.removeIncomingValue(BB);
	}
	sortPhiOperands(*SucBB);
	assert(BB->hasNPredecessors(0));
	DeleteDeadBlock(BB, &DTU);
	// BB->eraseFromParent();
	assert(SucBB->getParent());
	WorkList.insert(SucBB);
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
	auto& F = *SucBB->getParent();
	assert(!verifyFunction(F, &errs()));
#endif
	return true;
}

bool TrivialSimplifyCFGPass::tryRemoveSingleSuccessorBlockIfNotLatch(DomTreeUpdater &DTU,
		const bool allowPhiNewIncommingValues, BasicBlock *BB,
		llvm::SmallSetVector<WeakVH, 16> &WorkList) {
	if (BB == &BB->getParent()->getEntryBlock())
		return false; // can not remove entry point
	auto *SucBB = BB->getSingleSuccessor();
	if (!SucBB)
		return false;
	if (SucBB == BB) {
		return false; // can not remove self loop
	}
	auto &F = *BB->getParent();
	DTU.flush();
	auto &DT = DTU.getDomTree();
	bool isLoopLatch = DT.dominates(SucBB, BB);
	if (isLoopLatch)
		return false;
	LLVM_DEBUG(
			dbgs() << "tryRemoveSingleSuccessorBlockIfNotLatch BB:   "; BB->printAsOperand(dbgs()); dbgs() << "\n");
	bool blockEmpty = (BB->begin() == BB->end()
			|| BB->begin() == BB->getTerminator()->getIterator());
	if (!blockEmpty && SucBB->hasNPredecessors(1)) {
		SmallVector<std::pair<unsigned, MDNode*>> MDs;
		BB->getTerminator()->getAllMetadata(MDs);
		if (MergeBlockIntoPredecessor(SucBB, &DTU)) {
			mergeScavengedMetadata(MDs, BB->getTerminator());
			assert(BB->getParent());
			WorkList.insert(BB);
			onChangeCallback("TrivialSimplifyCFGPass - tryRemoveSingleSuccessorBlockIfNotLatch - MergeBlockIntoPredecessor", F);
			return true;
		}
	}
	if (!blockEmpty)
		return false;

	auto *SinglePredBB = BB->getSinglePredecessor();

	if (SinglePredBB) {
		if (tryRemoveSingleSuccessorSinglePredecessorBlock(
				DTU, BB, SinglePredBB, SucBB, WorkList)) {
			onChangeCallback("TrivialSimplifyCFGPass - "
							 "tryRemoveSingleSuccessorBlockIfNotLatch - "
							 "MergeBlockIntoPredecessor",
							 F);
			return true;
		}
		return false;
	} else if (BB->hasNPredecessors(0)) {
		return false;
	} else if (allowPhiNewIncommingValues || SucBB->phis().empty()) {
		if (tryRemoveSingleSuccessorManyPredecessorBlock(DTU, BB, SucBB,
														 WorkList)) {
			onChangeCallback("TrivialSimplifyCFGPass - "
							 "tryRemoveSingleSuccessorBlockIfNotLatch - "
							 "tryRemoveSingleSuccessorManyPredecessorBlock",
							 F);
			return true;
		}

		return false;
	}
	return false;
}

static bool trySimplifyTerminator(IRBuilder<> &Builder, DomTreeUpdater &DTU,
		BasicBlock &BB, llvm::SmallSetVector<WeakVH, 16> &worklist) {
	auto Term = BB.getTerminator();
	if (!Term) {
		errs() << BB << "\n";
		throw std::runtime_error(
				"AssertionError: Each block must have terminator");
	}
	if (auto br = dyn_cast<BranchInst>(Term)) {
		if (br->isConditional()) {
			int _newSuc = -1;
			int _sucToRm = -1;
			if (br->getSuccessor(0) == br->getSuccessor(1)) {
				// br c, bb0, bb0 -> br bb0
				_newSuc = 0;
				_sucToRm = 1;
			} else if (auto C = dyn_cast<ConstantInt>(br->getCondition())) {
				if (C->getZExtValue()) {
					// br 1, bb0, bb1 -> br bb0
					_newSuc = 0;
					_sucToRm = 1;
				} else {
					// br 0, bb0, bb1 -> br bb1
					_newSuc = 1;
					_sucToRm = 0;
				}
			}
			BasicBlock *NewSuc =
					_newSuc == -1 ? nullptr : br->getSuccessor(_newSuc);
			if (NewSuc != nullptr) {
				LLVM_DEBUG(
						dbgs() << "trySimplifyTerminator: removing cond branc in "; BB.printAsOperand(dbgs()); dbgs() << '\n');
				Builder.SetInsertPoint(br);
				auto *newBr = Builder.CreateBr(NewSuc);
				scavengeTerminatorMetadata(br, newBr);

				assert(_sucToRm == 0 || _sucToRm == 1);
				BasicBlock *sucToRm = br->getSuccessor(_sucToRm);
				for (PHINode &PHI : make_early_inc_range(sucToRm->phis())) {
					PHI.removeIncomingValue(&BB, true);
				}
				if (sucToRm != NewSuc) {
					DTU.applyUpdates(
							{ { DominatorTree::Delete, &BB, sucToRm } });
				}
				br->eraseFromParent();
#ifdef DBG_VERIFY_AFTER_EVERY_MODIFICATION
				auto& F = *BB.getParent();
				assert(!verifyFunction(F, &errs()));
#endif
				return true;
			}
		}
	}
	return false;
}

TrivialSimplifyCFGPass::TrivialSimplifyCFGPass(
		bool pruneSinglePredSingleSucBlocks, bool allowPhiNewIncommingValues, IrChangeCallbackFn* dbgIrCfgSimplifyChangeCallbackFn) :
		pruneSinglePredSingleSucBlocks(pruneSinglePredSingleSucBlocks), allowPhiNewIncommingValues(
				allowPhiNewIncommingValues), _dbgIrCfgSimplifyChangeCallbackFn(dbgIrCfgSimplifyChangeCallbackFn) {
}

void TrivialSimplifyCFGPass::onChangeCallback(const std::string & ruleName, llvm::Function & F) {
	if (_dbgIrCfgSimplifyChangeCallbackFn) {
		(*_dbgIrCfgSimplifyChangeCallbackFn)(ruleName, F);
	}
}

llvm::PreservedAnalyses TrivialSimplifyCFGPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	auto &DT = AM.getResult<DominatorTreeAnalysis>(F);
	DomTreeUpdater DTU(DT, DomTreeUpdater::UpdateStrategy::Lazy);
	IRBuilder<> Builder(F.getContext());
	bool Changed = false;
	if (EliminateUnreachableBlocks(F, &DTU, false)) {
		onChangeCallback("TrivialSimplifyCFGPass - EliminateUnreachableBlocks", F);
		Changed = true;
	}
	for (BasicBlock &BB : F) {
		if (BB.getSinglePredecessor())
			if (FoldSingleEntryPHINodes(&BB)) {
				onChangeCallback("TrivialSimplifyCFGPass - FoldSingleEntryPHINodes", F);
				Changed = true;
			}
	}
	llvm::SmallSetVector<WeakVH, 16> WorkList;
	for (BasicBlock &BB : F) {
		assert(BB.getParent());
		WorkList.insert(&BB);
	}

	while (!WorkList.empty()) {
		BasicBlock *BB = dyn_cast_or_null<BasicBlock>(WorkList.pop_back_val());
		if (!BB)
			continue;
		assert(BB->getParent());
		// :attention: trySimplifyTerminator is required because previous opt may generate
		// conditional br to same successor causes issues for rest of transformations like llvm::SimplifyCFG
		if (trySimplifyTerminator(Builder, DTU, *BB, WorkList)) {
			onChangeCallback("TrivialSimplifyCFGPass - trySimplifyTerminator", F);
			Changed = true;
		}
		if (pruneSinglePredSingleSucBlocks)
			if (tryRemoveSingleSuccessorBlockIfNotLatch(DTU,
					allowPhiNewIncommingValues, BB, WorkList)) {
				Changed = true;
			}
	}
	DTU.flush();

	if (Changed) {
		PreservedAnalyses PA;
		PA.preserve<DominatorTreeAnalysis>();
		return PA;
	} else {
		return PreservedAnalyses::all();
	}

}
}
