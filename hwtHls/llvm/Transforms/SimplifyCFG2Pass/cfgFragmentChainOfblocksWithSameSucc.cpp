#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/cfgFragmentChainOfblocksWithSameSucc.h>
#include <llvm/ADT/SmallSet.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>


using namespace llvm;

namespace hwtHls {

CfgFragmentChainOfblocksWithSameSucc::CfgFragmentChainOfblocksWithSameSucc() :
		exit(nullptr) {
}

using BasicBlockAndBrCond = CfgFragmentChainOfblocksWithSameSucc::BasicBlockAndBrCond;
BasicBlock* CfgFragmentChainOfblocksWithSameSuccAddBlock(BasicBlock &BB,
		BasicBlock &exit,
		llvm::SmallVector<BasicBlockAndBrCond> &blocksFromSearch, bool addToBlocksFromSearch) {
	assert(&exit != nullptr);
	assert(&BB != &exit);
	assert(&BB != nullptr);
	auto Term = dyn_cast<BranchInst>(BB.getTerminator());
	if (!Term) {
		return nullptr;
	} else if (&exit == Term->getSuccessor(0)) {
		BasicBlock *nextBB = nullptr;
		Value * Cond = nullptr;
		if (Term->isConditional()) {
			nextBB = Term->getSuccessor(1);
			Cond = Term->getCondition();
		} else {
			nextBB = Term->getSuccessor(0);
		}
		if (addToBlocksFromSearch)
			blocksFromSearch.push_back(BasicBlockAndBrCond(&BB, Cond, false));
		return nextBB;
	} else if (Term->isConditional() && &exit == Term->getSuccessor(1)) {
		auto *nextBB = Term->getSuccessor(0);
		if (addToBlocksFromSearch)
			blocksFromSearch.push_back(
				BasicBlockAndBrCond(&BB, Term->getCondition(), true));
		return nextBB;
	} else {
		// BB has no jump to exit, which should be a common direct successor of all blocks
		return nullptr;
	}
}

std::optional<CfgFragmentChainOfblocksWithSameSucc> CfgFragmentChainOfblocksWithSameSucc::detect(
		BasicBlock &exitBB) {
	if (pred_empty(&exitBB))
		return {};

	CfgFragmentChainOfblocksWithSameSucc res;
	res.exit = &exitBB;
	BasicBlock *_BB = *predecessors(&exitBB).begin(); // pick any predecessor block
	auto *BB = _BB;
	std::set<BasicBlock*> seen;
	llvm::SmallVector<BasicBlockAndBrCond> blocksFromUpSearch; // in bottom to top order
	if (BB == &exitBB)
		return {}; // exitBB itself is a loop this can not be a linear sequence of predecessors

	// search up
	for (;;) {
		if (seen.contains(BB)) {
			// BB is a part of cycle and thus it can not be a linear sequence
			break;
		} else {
			seen.insert(BB);
		}
		CfgFragmentChainOfblocksWithSameSuccAddBlock(*BB, *res.exit,
				blocksFromUpSearch, true);
		if (pred_size(BB) != 1) {
			// not a continuation of linear sequence
			break;
		}
		BB = *predecessors(BB).begin();
		if (BB == &exitBB)
			break; // exitBB jumps at the first block in predecessor sequence
	}
	// convert from bottom to top order to top to bottom order
	for (BasicBlockAndBrCond &BBItem : reverse(blocksFromUpSearch)) {
		res.blocks.push_back(BBItem);
	}
	BB = _BB;
	seen.erase(BB);
	// search down
	bool first = true;
	for (;;) {
		if (!res.blocks.empty() && BB != res.blocks[0].BB && pred_size(BB) != 1)
			return {}; // some block in chain has predecessor which is not a predecessor in chain
		if (seen.contains(BB)) {
			return {}; // cycle found, this can not be linear sequence of blocks ending in exit
		} else {
			seen.insert(BB);
		}

		BB = CfgFragmentChainOfblocksWithSameSuccAddBlock(*BB, *res.exit,
				res.blocks, !first);
		first = false;
		if (!BB) {
			return {};
		} else if (BB == res.exit) {
			break;
		}
		// else continue search on next successor which is not exit
	}

	if (res.blocks.size() != pred_size(&exitBB)) {
		return {};
	}
	return res;
}

}
