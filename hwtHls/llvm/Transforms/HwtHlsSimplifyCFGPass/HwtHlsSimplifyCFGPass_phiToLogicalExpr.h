#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/HwtHlsSimplifyCFGPass/cfgFragmentChainOfblocksWithSameSucc.h>

namespace llvm {
class DomTreeUpdater;
class AssumptionCache;
}

namespace hwtHls {

/*
 * Try to find linear chain of predecessors and convert PHIs of this block
 * to bit counts, logic operator or selects.
 * Attempt to hoist all from predecessor chain to top most predecessor;
 * If all PHIs are removed attempt to merge predecessor blocks;
 * */
bool HwtHlsSimplifyCFGPass_phiToLogicalExpr(llvm::IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, const llvm::DataLayout &DL,
		llvm::AssumptionCache *AC, llvm::BasicBlock &exitBB, bool & exprChanged);

enum class PhiToLogicalExprOptLevel {
	ONLY_identity_hwtHls_mergableFunction = 0,
	ONLY_identity_fshl_cttz_hwtHls_mergableFunction = 1,
	ALL = 2,
};
/*
 * :param onlyRewriteHighOrderFns: if true only patterns for fshl, cttz,
 *      hwtHls.mergableFunction.statePlusMaskedData, identity,
 *      this option exists because offten we want to extract these functions
 *      even if it won't lead to CFG simplification
 * :returns: null if rewrite failed else returns new rewritten value
 * */
llvm::Value* HwtHlsSimplifyCFGPass_phiToLogicalExpr(llvm::IRBuilderBase &Builder,
		const llvm::DataLayout &DL, llvm::AssumptionCache *AC,
		CfgFragmentChainOfblocksWithSameSucc &predecChain, llvm::PHINode &PHI,
		PhiToLogicalExprOptLevel optLvl);

}
