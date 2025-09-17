#include <hwtHls/llvm/Transforms/LoopFlattenUsingIfPass/findAssociatedPhis.h>
#include <algorithm>
#include <llvm/ADT/SetVector.h>

using namespace llvm;

namespace hwtHls {

struct ScoreAndRank {
	size_t score; // main score, more = better
	size_t rank; // order of original item to make winner selection deterministic
};

void countHowManytimesValueIsDrivenFromPhi(llvm::Loop &L, llvm::Instruction &I,
		size_t exprDepth, std::set<Instruction*> &seen,
		std::map<Instruction*, ScoreAndRank> &score) {
	if (!L.contains(I.getParent()))
		return; // driver outside of parent loop, this can not lead to parent phi

	auto _score = score.find(&I);
	if (_score != score.end()) {
		size_t curScore = _score->second.score;
		size_t thisScore = std::numeric_limits<size_t>::max() - exprDepth;
		_score->second.score = std::max(curScore, thisScore);
		return;
	}

	if (seen.find(&I) != seen.end()) {
		// prevent looping on loop header phis
		return;
	} else {
		seen.insert(&I);
	}

	for (Use &Op : I.operands()) {
		if (Op.get()->getType() == I.getType())
			if (auto OpI = dyn_cast<Instruction>(Op.get())) {
				countHowManytimesValueIsDrivenFromPhi(L, *OpI, exprDepth + 1,
						seen, score);
			}
	}
}

void collectBlocksUntilLoopEnd(llvm::Loop &L, SetVector<BasicBlock*> &seen,
		BasicBlock &BB) {
	if (&BB == L.getHeader())
		return; // header is start of new iteration, which is after loop end
	if (seen.insert(&BB)) {
		// analyzing also loop exit block, which is not part of the loop
		if (!L.contains(&BB))
			return;
		for (auto Suc : successors(&BB)) {
			collectBlocksUntilLoopEnd(L, seen, *Suc);
		}
	}
}

std::map<PHINode*, PHINode*> findAssociatedPhis(llvm::Loop &LParent,
		llvm::Loop &LChild) {
	std::map<PHINode*, PHINode*> childToParentPhi;
	auto childHeader = LChild.getHeader();
	auto childPhis = childHeader->phis();
	if (childPhis.begin() == childPhis.end()) {
		// there is nothing to associate with
		return childToParentPhi;
	}

	SetVector<BasicBlock*> blocksAfterChildLoop;
	SmallVector<BasicBlock*> ExitBlocks;
	LChild.getExitBlocks(ExitBlocks);
	for (auto BB : ExitBlocks)
		collectBlocksUntilLoopEnd(LParent, blocksAfterChildLoop, *BB);

	// :note: except for PHI incoming values from outside of after child loop section
	// :note: this expects LoopSimplify normal form where all loop liveouts have phi in exit block
	auto isUsedAfterChildLoop = [&](PHINode &phi) {
		for (auto &U : phi.uses()) {
			if (auto UInst = dyn_cast<Instruction>(U.getUser())) {
				auto Ubb = UInst->getParent();
				if (auto UPhi = dyn_cast<PHINode>(UInst)) {
					if (!LParent.contains(Ubb)) {
						// this is liveout of parent loop
						return true;
					} else {
						for (size_t i = 0; i < UPhi->getNumIncomingValues();
								++i) {
							if (UPhi->getIncomingValue(i) == &phi
									&& blocksAfterChildLoop.contains(Ubb)) {
								return true; // used internally in phi inside of after child loop section
							}
						}
						// used only on edge from child loop or section before it
					}
				} else {
					if (blocksAfterChildLoop.contains(Ubb))
						return true; // used internally in section after loop
				}
			}
		}
		return false;
	};

	using ScoreDict = std::map<Instruction*, ScoreAndRank>;
	ScoreDict availablePhiScore;
	size_t rank = 0;
	for (PHINode &parentPhi : LParent.getHeader()->phis()) {
		if (!isUsedAfterChildLoop(parentPhi))
			availablePhiScore[&parentPhi] = { 0, rank++ };
	}

	if (availablePhiScore.empty())
		return childToParentPhi;

	for (PHINode &childPhi : childHeader->phis()) {
		std::set<Instruction*> seen;
		countHowManytimesValueIsDrivenFromPhi(LParent, childPhi, 0, seen,
				availablePhiScore);

		auto bestCandidate = std::max_element(availablePhiScore.begin(),
				availablePhiScore.end(),
				[](ScoreDict::reference &v0, ScoreDict::reference &v1) {
					if (v0.second.score == v1.second.score)
						return v0.second.rank < v1.second.rank;
					else
						return v0.second.score < v1.second.score;
				});

		if (bestCandidate->second.score) {
			childToParentPhi[&childPhi] = dyn_cast<PHINode>(
					bestCandidate->first);
			assert(
					childPhi.getType() == bestCandidate->first->getType()
							&& "If type is different score should be 0 and we should never get there");
			availablePhiScore.erase(bestCandidate);
		}

		if (availablePhiScore.empty())
			break;
		// reset score for next phi search
		for (auto &score : availablePhiScore) {
			score.second.score = 0;
		}
	}

	return childToParentPhi;
}

}
