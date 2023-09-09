#include <hwtHls/llvm/Transforms/trivialSimplifyCFGPass.h>

#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
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
		llvm::SmallSetVector<BasicBlock*, 16> &WorkList) {
	// Remove empty basic block if has single successor and predecessor and may be replaced by predecessor in successor PHIs
	if (BB->begin() == BB->end() || &*BB->begin() == BB->getTerminator()
			|| ++BB->begin() == BB->end()) {
		if (auto *SucBB = BB->getSingleSuccessor()) {
			if (SucBB == BB) {
				return false; // can not remove self loop
			}
			if (auto *PredBB = BB->getSinglePredecessor()) {
				// detect if PHIs are compatible
				SmallVector<PHINode*, 4> alreadyHasTheValueInPhis;
				for (PHINode &SucPhi : SucBB->phis()) {
					for (auto *SucPredBB : SucPhi.blocks()) {
						auto SucPredVal = SucPhi.getIncomingValueForBlock(
								&*SucPredBB);
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

				// update PHIs
				for (PHINode &SucPhi : SucBB->phis()) {
					if (std::find(alreadyHasTheValueInPhis.begin(),
							alreadyHasTheValueInPhis.end(), &SucPhi)
							!= alreadyHasTheValueInPhis.end())
						SucPhi.removeIncomingValue(BB, false);
				}
				PredBB->getTerminator()->replaceSuccessorWith(BB, SucBB); // guaranteed that there is only one brach with this block as a target
				// because there is a single predecessor
				BB->replaceAllUsesWith(PredBB); // replace in other PHIs, which effectively disconnect this from predecessor
				assert(BB->hasNPredecessors(0));
				scavengeTerminatorMetadata(BB->getTerminator(),
						SucBB->getTerminator());
				BB->eraseFromParent();
				//DeleteDeadBlock(BB); // this causes segfault as it expect for PHIs to have this block in operands
				WorkList.insert(PredBB);
				WorkList.insert(SucBB);
				return true;
			}
		}
	}
	return false;
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
		Changed |= tryRemoveSingleSuccessorSinglePredecessorBlock(BB, WorkList);
	}
	if (Changed) {
		PreservedAnalyses PA;
		return PA;
	} else {
		return PreservedAnalyses::all();
	}

}
}
