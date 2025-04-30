#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/IR/IRBuilder.h>
#include <hwtHls/llvm/Transforms/SimplifyCFG2Pass/cfgFragmentChainOfblocksWithSameSucc.h>

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
bool SimplifyCFG2Pass_phiToLogicalExpr(llvm::IRBuilderBase &Builder,
		llvm::DomTreeUpdater &DTU, const llvm::DataLayout &DL,
		llvm::AssumptionCache *AC, llvm::BasicBlock &exitBB);

/*
 * :returns: null if rewrite failed else returns new rewritten value
 * */
llvm::Value* SimplifyCFG2Pass_phiToLogicalExpr(llvm::IRBuilderBase &Builder,
		const llvm::DataLayout &DL, llvm::AssumptionCache *AC,
		CfgFragmentChainOfblocksWithSameSucc &predecChain, llvm::PHINode &PHI);

}
