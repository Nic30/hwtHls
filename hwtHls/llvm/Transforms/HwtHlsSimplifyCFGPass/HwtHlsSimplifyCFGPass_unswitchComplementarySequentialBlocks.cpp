#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentComplementarySequentialBlocks.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/HwtHlsSimplifyCFGUtils.h>
#include <hwtHls/llvm/Transforms/utils/cfgUtils.h>

using namespace llvm;

namespace hwtHls {

bool HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_tryHoistFromBB1(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		CfgFragmentComplementarySequentialBlocks &cfgFrag, bool &exprChanged) {
	/* * if we can hoist from bb1 to bb0 and bbC1 does not depend on bbC0
	 *   transform
	 * .. code-block:: llvm
	 *       bb0
	 *       |  \
	 *     bb.c0 |
	 *       |  /
	 *       bb1
	 *       |  \
	 *       | bb.c1
	 *       |   |
	 *
	 * to:
	 * .. code-block:: llvm
	 *       bb0
	 *       |    \
	 *     bb.c0 bb.c1
	 *       |     |
	 *
	 */
	bool bb1HoistSuccess = true;
	auto bb0Term = dyn_cast<BranchInst>(cfgFrag.bb0->getTerminator());
	assert(bb0Term);
	Builder.SetInsertPoint(bb0Term);
	bool bbC0hoistAttempted = false;
	for (auto &phi : make_early_inc_range(cfgFrag.bb1->phis())) {
		assert(phi.getNumIncomingValues() == 2 && "expects bb0, bbC0");
		auto bbC0v = phi.getIncomingValueForBlock(cfgFrag.bbC0);
		if (auto bbC0i = dyn_cast<Instruction>(bbC0v)) {
			if (bbC0i->getParent() == cfgFrag.bbC0) {
				if (bbC0hoistAttempted) {
					bb1HoistSuccess = false;
					break;
				} else {
					exprChanged |= tryHoistCheapInstsAtBlockBegin(*cfgFrag.bbC0,
							bb0Term->getIterator());
					bbC0hoistAttempted = true;
					if (bbC0i->getParent() == cfgFrag.bbC0) {
						bb1HoistSuccess = false;
						break;
					}
				}
			}
		}
		// transform PHINode to SelectInst before bb0Term
		auto tVal = bbC0v;
		auto fVal = phi.getIncomingValueForBlock(cfgFrag.bb0);
		if (!cfgFrag.bbC0isTrueSuccessor)
			std::swap(tVal, fVal);
		auto sel = Builder.CreateSelect(bb0Term->getCondition(), tVal, fVal);
		sel->takeName(&phi);
		phi.replaceAllUsesWith(sel);
		phi.eraseFromParent();
		exprChanged = true;
	}
	if (bb1HoistSuccess) {
		// if hoist of phis succeeded  now try to hoist
		auto instrNotInBBC0 = [&cfgFrag](Instruction &I) {
			return I.getParent() != cfgFrag.bbC0;
		};
		exprChanged |= tryHoistCheapInstsAtBlockBegin(*cfgFrag.bb1, bb0Term->getIterator(),
				instrNotInBBC0);
		if (cfgFrag.bb1->size() != 1 && !bbC0hoistAttempted) {
			exprChanged |= tryHoistCheapInstsAtBlockBegin(*cfgFrag.bbC0,
					bb0Term->getIterator());
			bbC0hoistAttempted = true;
			exprChanged |= tryHoistCheapInstsAtBlockBegin(*cfgFrag.bb1, bb0Term->getIterator(),
					instrNotInBBC0);
		}
		bb1HoistSuccess = cfgFrag.bb1->size() == 1;
	}
	if (bb1HoistSuccess) {
		// bb1 now has only terminator, there are no deps between blocks after bb0
		// thus we can rewrite cfg
		auto bb1 = cfgFrag.bb1;
		auto bb1exit = bb1->getTerminator()->getSuccessor(
				cfgFrag.bbC0isTrueSuccessor ? 0 : 1);
		assert(bb1exit != cfgFrag.bbC1);
		// bbC0 will now jump directly to bb1exit
		replaceSuccessorWith(*cfgFrag.bbC0, DTU, bb1, bb1exit);

		// bb0 will no jump directly to bbC1 instead of bb1
		replaceSuccessorWith(*cfgFrag.bb0, DTU, bb1, cfgFrag.bbC1);

		// bb1 will become unreachable and will not jump anywhere
		// we do not delete it immediately to avoid breaking the parent iterator over blocks in function
		DTU.applyUpdates( { //
				{ DominatorTree::Delete, bb1, bb1exit }, //
						{ DominatorTree::Delete, bb1, cfgFrag.bbC1 } //
				});
		auto bb1term = bb1->getTerminator();
		Builder.SetInsertPoint(bb1term);
		Builder.CreateUnreachable();
		bb1term->eraseFromParent();
		return true;
	}
	return false;
}

bool HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks(
		llvm::IRBuilderBase &Builder, llvm::DomTreeUpdater &DTU,
		llvm::BasicBlock &BB0, bool &exprChanged) {
	auto _cfgFrag = CfgFragmentComplementarySequentialBlocks::detect(
			DTU.getDomTree(), BB0);
	if (!_cfgFrag.has_value())
		return false;
	auto &cfgFrag = _cfgFrag.value();

	if (HwtHlsSimplifyCFGPass_unswitchComplementarySequentialBlocks_tryHoistFromBB1(
			Builder, DTU, cfgFrag, exprChanged))
		return true;
	// * if bb1 and bbC1 have common successor (split bbC1, reroute bb1 to jump to it instead of bb.exit,
	//   update condition in new common successor to be or of bb1 and bbC1 conditions)
	// llvm_unreachable("[todo]");
	return false;
}
}
