#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_normalizeBrCond.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFG_priv.h>

#include <llvm/IR/PatternMatch.h>

using namespace llvm;
using namespace llvm::PatternMatch;

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_normalizeBrCond(BranchInst *BI) {
	bool changed = false;
	if (BI->isConditional()) {
		auto C = BI->getCondition();
		bool cIsNegated = false;
		Value *cUnNegated;
		while (match(C, m_Not(m_Value(cUnNegated)))) {
			C = cUnNegated;
			changed = true;
			cIsNegated = !cIsNegated;
		}
		if (changed) {
			if (cIsNegated)
				BI->swapSuccessors();
			BI->setCondition(C);
		}
	}
	return changed;
}

}
