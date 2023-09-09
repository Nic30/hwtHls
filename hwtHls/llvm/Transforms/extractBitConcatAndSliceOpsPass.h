#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  A pass to extract bit replications, concatenations and slices as a hwtHls.bit* call.
 */
class ExtractBitConcatAndSliceOpsPass: public llvm::PassInfoMixin<
		ExtractBitConcatAndSliceOpsPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
