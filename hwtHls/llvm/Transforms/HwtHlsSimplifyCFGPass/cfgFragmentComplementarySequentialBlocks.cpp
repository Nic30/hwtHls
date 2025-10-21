#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentComplementarySequentialBlocks.h>
#include <llvm/IR/Instructions.h>

using namespace llvm;

namespace hwtHls {

CfgFragmentComplementarySequentialBlocks::CfgFragmentComplementarySequentialBlocks() :
		bbC0isTrueSuccessor(false), bb0(nullptr), bbC0(nullptr),  bb1(
				nullptr), bbC1(nullptr) {
}

std::optional<CfgFragmentComplementarySequentialBlocks> CfgFragmentComplementarySequentialBlocks::detect(
		llvm::DominatorTree &DT, llvm::BasicBlock &BB0) {
	CfgFragmentComplementarySequentialBlocks pattern;
	pattern.bb0 = &BB0;
	auto *bb0Term = dyn_cast<BranchInst>(BB0.getTerminator());
	if (!bb0Term)
		return {};
	if (!bb0Term->isConditional())
		return {};

	pattern.bbC0 = bb0Term->getSuccessor(0);
	pattern.bb1 = bb0Term->getSuccessor(1);
	if (pattern.bbC0->getSingleSuccessor() == pattern.bb1) {
		/*
		 * .. code-block:: text
		 *       bb0
		 *       |  \
		 *     bb.c0 |
		 *       |  /
		 *       bb1
		 *       |  \
		 *       | bb.c1
		 *       |   |
		 */
		pattern.bbC0isTrueSuccessor = true;
	} else {
		std::swap(pattern.bbC0, pattern.bb1);
		/*
		 * .. code-block:: text
		 *       bb0
		 *       |  \
		 *       | bb.c0
		 *       |  /
		 *       bb1
		 *       |  \
		 *     bb.c1 |
		 *       |   |
		 */
		pattern.bbC0isTrueSuccessor = false;
		if (pattern.bbC0->getSingleSuccessor() != pattern.bb1)
			return {};
	}
	if (!pattern.bbC0->hasNPredecessors(1))
		return {};
	if (!pattern.bb1->hasNPredecessors(2))
		return {};

	auto bb1Term = dyn_cast<BranchInst>(pattern.bb1->getTerminator());
	if (!bb1Term)
		return {};
	if (!bb1Term->isConditional())
		return {};

	Value *cond0 = bb0Term->getCondition();
	Value *cond1 = bb1Term->getCondition();
	if (cond0 != cond1)
		return {};
	if (pattern.bbC0isTrueSuccessor) {
		pattern.bbC1 = bb1Term->getSuccessor(1);
	} else {
		pattern.bbC1 = bb1Term->getSuccessor(0);
	}
	if (!pattern.bbC1->hasNPredecessors(1))
		return {};

	return pattern;
}

}
