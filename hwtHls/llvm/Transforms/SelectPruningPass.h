#pragma once

#include <set>
#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 * Recursively prune SelectInst operands using knowledge collected from condition operands.
 */
class SelectPruningPass: public llvm::PassInfoMixin<SelectPruningPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}
