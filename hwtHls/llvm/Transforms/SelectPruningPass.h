#pragma once

#include <set>
#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/Instructions.h>
#include <hwtHls/llvm/Transforms/utils/dceWorklist.h>

//#include <hwtHls/llvm/targets/intrinsic/concatMemberVector.h>
#include <hwtHls/llvm/Transforms/bitwidthReducePass/utils.h>


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
