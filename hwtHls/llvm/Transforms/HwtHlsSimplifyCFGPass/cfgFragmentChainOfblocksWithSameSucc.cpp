#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentChainOfblocksWithSameSucc.h>

#include <llvm/ADT/SmallSet.h>
#include <llvm/ADT/STLExtras.h>
#include <llvm/IR/Instructions.h>
#include <llvm/Transforms/Utils/BasicBlockUtils.h>

using namespace llvm;

namespace hwtHls {

CfgFragmentChainOfblocksWithSameSucc::CfgFragmentChainOfblocksWithSameSucc() :
		exit(nullptr) {
}

std::pair<BasicBlock*,
		std::optional<CfgFragmentChainOfblocksWithSameSucc::BasicBlockAndBrCond>> CfgFragmentChainOfblocksWithSameSucc::detectOne(
		BasicBlock &BB, BasicBlock &exit) {
	assert(&exit != nullptr);
	assert(&BB != &exit);
	assert(&BB != nullptr);
	auto Term = dyn_cast<BranchInst>(BB.getTerminator());
	if (!Term) {
		return {nullptr, {}};
	} else if (&exit == Term->getSuccessor(0)) {
		BasicBlock *nextBB = nullptr;
		Value *Cond = nullptr;
		if (Term->isConditional()) {
			nextBB = Term->getSuccessor(1);
			Cond = Term->getCondition();
		} else {
			nextBB = Term->getSuccessor(0);
		}
		return {nextBB, BasicBlockAndBrCond(&BB, Cond, false)};
	} else if (Term->isConditional() && &exit == Term->getSuccessor(1)) {
		auto *nextBB = Term->getSuccessor(0);
		return {nextBB, BasicBlockAndBrCond(&BB, Term->getCondition(), true)};
	} else {
		// BB has no jump to exit, which should be a common direct successor of all blocks
		return {nullptr, {}};
	}
}


}
