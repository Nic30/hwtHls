#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/SimplifyCFG2Pass_aggresiveStoreSink.h>
#include <algorithm>

#include <llvm/ADT/SmallVector.h>
#include <llvm/ADT/SetVector.h>
#include <llvm/ADT/DenseMap.h>

#include <llvm/Analysis/IteratedDominanceFrontier.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IR/CFG.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/constBitPartsAnalysis.h>
#include <hwtHls/llvm/targets/intrinsic/bitrange.h>

#define DEBUG_TYPE "simplifycfg2"
using namespace llvm;

namespace hwtHls {

/*
 * Search bottom->up in CFG and find first block with properly (strictly) dominates BBBottom
 *
 * :param seen: set used to avoid hanging if there is a loop in searched CFG
 * :param BB: block where search start
 * :param BBBottom: block which must be be dominated by result
 * :return: first found block which does properly (strictly) dominate BBBottom
 */
BasicBlock* searchPotentialCFGDiamondEntry(DominatorTree &DT,
		std::set<BasicBlock*> &seen, BasicBlock &BBBottom, BasicBlock &BB) {
	if (DT.properlyDominates(&BB, &BBBottom)) {
		return &BB;
	} else {
		for (BasicBlock *pred : predecessors(&BB)) {
			if (seen.find(pred) == seen.end()) {
				seen.insert(pred);
				if (auto *found = searchPotentialCFGDiamondEntry(DT, seen,
						BBBottom, *pred)) {
					return found;
				}
			}
		}
	}
	return nullptr;
}

bool IsSelfLoop(const BasicBlock &BB) {
	for (const BasicBlock *suc : successors(&BB)) {
		if (&BB == suc)
			return true;
	}
	return false;
}

/*
 * For each transitive successor of the BBTop and
 * check if each block between BBTop and BBBottom is dominated by BBTop and dominates BBBottom
 * == the subgraph between BBTop and BBBottom is enclosed
 * */
bool searchCFGDiamondBlocks(DominatorTree &DT, SetVector<BasicBlock*> &found,
		BasicBlock &BBTop, BasicBlock &BBBottom, BasicBlock &Cur) {
	if (&Cur == &BBBottom || found.count(&Cur))
		return true;

	if (DT.dominates(&BBTop, &Cur)) {
		found.insert(&Cur);
		for (auto suc : successors(&Cur)) {
			if (suc == &BBTop) {
				// odd case where BBTop is a header of loop but it is somehow
				// first fully dominating block for BBBottom which has multiple predecessors
				// this may happen only if blocks with more than 2 successors
				return false;
			}
			if (!searchCFGDiamondBlocks(DT, found, BBTop, BBBottom, *suc)) {
				return false;
			}
		}
		return true;
	} else {
		return false;
	}
}


bool SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData(
		llvm::DomTreeUpdater &DTU, llvm::BasicBlock &BBBottom) {
	/*
	 * The search start from bottom block with PHIs then it divides blocks based on dominance to 2 groups
	 * and check left and right side if there are some bits which do have different polarity.
	 * * The search of splitting block starts on first predecessor and then goes up while it
	 *   is post-dominated by BBBottom.
	 * * If such a bit is found it means that the it could be replaced with the value of branch condition in that block.
	 * * The replacing bit is an "and" of all predecessor branch conditions.
	 * */
	return false;
	if (!DTU.hasDomTree() || BBBottom.phis().begin() == BBBottom.phis().end()
			|| IsSelfLoop(BBBottom))
		return false; // can not optimize or nothing to optimize

	auto &DT = DTU.getDomTree();
	// find diamond pattern of interest
	SetVector<BasicBlock*> diamondBlocks;
	std::set<BasicBlock*> diamondTopSearchSeen;
	auto BBBottomPreds = predecessors(&BBBottom);
	if (BBBottomPreds.empty())
		return false; // BBBottom can not be diamond bottom because it has no predecessors

	BasicBlock &BBBottomPred = **BBBottomPreds.begin();
	BasicBlock *BBTop = searchPotentialCFGDiamondEntry(DT, diamondTopSearchSeen,
			BBBottom, BBBottomPred);
	if (!BBTop || IsSelfLoop(*BBTop))
		return false; // no suitable diamond entry

	SetVector<BasicBlock*> DiamondBlocks;
	if (!searchCFGDiamondBlocks(DT, DiamondBlocks, BBBottom, *BBTop, *BBTop)) {
		return false; // some block was not dominated by BBTop (there is some other entry to "diamond")
	}

	// for each PHI of the block check if some bits have constant
	// value which is by this PHI.
	auto CBAHandle = [](const Instruction &I) {
		if (auto *CI = dyn_cast<CallInst>(&I)) {
			return bool(IsBitConcat(CI) || IsBitConcat(CI));
		}
		return false;
	};

	ConstBitPartsAnalysisContext CBA(CBAHandle);
	bool Changed = false;
	for (PHINode &Phi : BBBottom.phis()) {
		CBA.visitValue(&Phi);
		// create map for blocks up in diamond which maps block to a known bits of phi
		// search the blocks where bit has opposite value on T/F branch
		// if every other block non-dominated by this block has some specific value (same as in T/F branch)
		// we can replace this bit with the value of branch condition leading to this block
		// https://rd.springer.com/chapter/10.1007/3-540-48294-6_12
		// https://dl.acm.org/doi/10.1145/207110.207154
		auto &F = *BBBottom.getParent();
		errs() << F << "\n";
		errs() << Phi << "\n";
		for (const auto& c: CBA.constraints) {
			if (c.first->getType()->isIntegerTy() && !isa<ConstantInt>(c.first)) {
				errs() << c.first << " " << *c.first << "\n";
				errs() << "    " << *c.second << "\n";
			}
		}

		writeCFGToDotFile(F, "SimplifyCFG2Pass_rewriteMaskPatternsFromCFGToData.dot", nullptr, nullptr);
		std::map<BasicBlock*, KnownBitRangeInfo> knownBitsInEachBlock;
		//auto getKnownBitRangeInfo = [&CBA, &knownBitsInEachBlock, &Phi, &BBBottom] (BasicBlock & Pred) {
		//	if (&Pred == &BBBottom) {
		//		return *CBA.constraints[Phi.getIncomingValueForBlock(&Pred)];
		//	}
		//	auto cur = knownBitsInEachBlock.find(&Pred);
		//	if (cur == knownBitsInEachBlock.end()) {
		//		if (auto* br = dyn_cast<BranchInst>(Pred.getTerminator())) {
		//			if (br->isConditional()) {
		//				auto* T = br->getSuccessor(0);
		//				auto* F = br->getSuccessor(1);
		//				llvm_unreachable("NotImplemted - merge from two branches with detecting cond pattern");
		//			}
		//		} else {
		//			llvm_unreachable("NotImplemted - merge from all branches ignoring cond pattern");
		//		}
        //
		//	}
		//	return *cur->second;
		//};
		//auto KnownBits = getKnownBitRangeInfo(BBTop);
		llvm_unreachable("NotImplemented use KnownBits to cut off bits which are defined"
				" to branch conditions and create final concatenation and replace original phi");
	}
	return Changed;
}

}
