#pragma once

#include <llvm/IR/Instructions.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/AssumptionCache.h>
#include <llvm/Analysis/LazyValueInfo.h>

namespace llvm {
class Function;
}

namespace hwtHls {

//===----------------------------------------------------------------------===//
//
// Simplified version of LowerSwitch which does not use pivoting and constructs linear chain
// of case blocks instead (which is then more simple to reduce in vreg-if-converter)
//===----------------------------------------------------------------------===//
class LowerSwitchWithIfChain: public llvm::PassInfoMixin<LowerSwitchWithIfChain> {
public:
	static bool LowerSwitch(llvm::Function &F, llvm::LazyValueInfo *LVI,
							llvm::AssumptionCache *AC);
	static void
	ProcessSwitchInst(llvm::SwitchInst *SI,
					  llvm::SmallPtrSetImpl<llvm::BasicBlock *> &DeleteList,
					  llvm::AssumptionCache *AC, llvm::LazyValueInfo *LVI);
	llvm::PreservedAnalyses run(llvm::Function &F,
								llvm::FunctionAnalysisManager &AM);
};

}
