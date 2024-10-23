#include <hwtHls/llvm/Transforms/trivialSimplifyCFGPass.h>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/CFG.h>

#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

#include <algorithm>

using namespace llvm;

namespace hwtHls {

void scavengeTerminatorMetadata(Instruction *br, Instruction *newBr) {
	SmallVector<std::pair<unsigned, MDNode*>> MDs;
	br->getAllMetadata(MDs);
	for (const auto &md : MDs) {
		assert(!newBr->hasMetadata(md.first));
		newBr->setMetadata(md.first, md.second);
	}
}

bool tryRemoveSingleSuccessorSinglePredecessorBlock(BasicBlock *BB,
		BasicBlock *PredBB, BasicBlock *SucBB,
		llvm::SmallSetVector<BasicBlock*, 16> &WorkList) {
	// Remove empty basic block if has single successor and predecessor and may be replaced by predecessor in successor PHIs
	// detect if PHIs are compatible
	SmallVector<PHINode*, 4> alreadyHasTheValueInPhis;
	for (PHINode &SucPhi : SucBB->phis()) {
		for (auto *SucPredBB : SucPhi.blocks()) {
			auto SucPredVal = SucPhi.getIncomingValueForBlock(&*SucPredBB);
			if (SucPredBB == PredBB) {
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

	// update successor PHIs
	for (PHINode &SucPhi : SucBB->phis()) {
		if (std::find(alreadyHasTheValueInPhis.begin(),
				alreadyHasTheValueInPhis.end(), &SucPhi)
				!= alreadyHasTheValueInPhis.end())
			SucPhi.removeIncomingValue(BB, false);
	}

	// guaranteed that there is only one branch with this block as a target
	PredBB->getTerminator()->replaceSuccessorWith(BB, SucBB);
	// because there is a single predecessor
	BB->replaceAllUsesWith(PredBB); // replace in other PHIs, which effectively disconnect this from predecessor
	assert(BB->hasNPredecessors(0));
	scavengeTerminatorMetadata(BB->getTerminator(), PredBB->getTerminator());
	BB->eraseFromParent();
	//DeleteDeadBlock(BB); // this causes segfault as it expect for PHIs to have this block in operands
	WorkList.insert(PredBB);
	WorkList.insert(SucBB);
	return true;
}
bool tryRemoveSingleSuccessorManyPredecessorBlock(BasicBlock *BB,
		BasicBlock *SucBB, llvm::SmallSetVector<BasicBlock*, 16> &WorkList) {
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
		WorkList.insert(PredBB);
	}
	for (auto &phi : SucBB->phis()) {
		phi.removeIncomingValue(BB);
	}
	assert(BB->hasNPredecessors(0));
	BB->eraseFromParent();
	WorkList.insert(SucBB);
	return true;

}

bool tryRemoveSingleSuccessorBlock(BasicBlock *BB,
		llvm::SmallSetVector<BasicBlock*, 16> &WorkList) {
	auto *SucBB = BB->getSingleSuccessor();
	if (!SucBB)
		return false;
	if (SucBB == BB) {
		return false; // can not remove self loop
	}
	bool blockEmpty = (BB->begin() == BB->end()
			|| BB->begin() == BB->getTerminator()->getIterator());
	if (!blockEmpty && SucBB->hasNPredecessors(1)) {
		if (MergeBlockIntoPredecessor(SucBB)) {
			WorkList.insert(BB);
			return true;
		}
	}
	if (!blockEmpty)
		return false;

	auto *SinglePredBB = BB->getSinglePredecessor();
	if (SinglePredBB) {
		return tryRemoveSingleSuccessorSinglePredecessorBlock(BB, SinglePredBB,
				SucBB, WorkList);
	} else if (BB->hasNPredecessors(0)) {
		return false;
	} else {

		return tryRemoveSingleSuccessorManyPredecessorBlock(BB, SucBB, WorkList);
	}
}

bool trySimplifyTerminator(BasicBlock &BB,
		llvm::SmallSetVector<BasicBlock*, 16> &worklist) {
	if (auto br = dyn_cast<BranchInst>(BB.getTerminator())) {
		if (br->isConditional() && br->getSuccessor(0) == br->getSuccessor(1)) {
			// br c, bb0, bb0 -> br bb0
			IRBuilder<> Builder(br);
			auto *newBr = Builder.CreateBr(br->getSuccessor(0));
			scavengeTerminatorMetadata(br, newBr);
			br->eraseFromParent();
			return true;
		}
	}
	return false;
}
TrivialSimplifyCFGPass::TrivialSimplifyCFGPass(
		bool pruneSinglePredSingleSucBlocks) :
		pruneSinglePredSingleSucBlocks(pruneSinglePredSingleSucBlocks) {
}
llvm::PreservedAnalyses TrivialSimplifyCFGPass::run(llvm::Function &F,
		llvm::FunctionAnalysisManager &AM) {
	bool Changed = false;
	Changed |= EliminateUnreachableBlocks(F, nullptr, false);
	for (BasicBlock &BB : F) {
		if (BB.getSinglePredecessor())
			Changed |= FoldSingleEntryPHINodes(&BB);
	}
	llvm::SmallSetVector<BasicBlock*, 16> WorkList;
	for (BasicBlock &BB : F) {
		WorkList.insert(&BB);
	}

	while (!WorkList.empty()) {
		BasicBlock *BB = WorkList.pop_back_val();
		// attention trySimplifyTerminator is required because previous opt may generate conditiona br to same successor causes issues for rest of transformations like llvm::SimplifyCFG
		if (trySimplifyTerminator(*BB, WorkList)) {
			Changed = true;
		}
		if (pruneSinglePredSingleSucBlocks)
			Changed |= tryRemoveSingleSuccessorBlock(BB, WorkList);
	}
	if (Changed) {
		PreservedAnalyses PA;
		return PA;
	} else {
		return PreservedAnalyses::all();
	}

}
}
