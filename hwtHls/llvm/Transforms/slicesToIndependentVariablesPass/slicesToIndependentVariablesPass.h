#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  A pass to convert variables which do have some bits driven or used independently to multiple variables.
 *  :note: This pass does something similar to SROA (https://www.llvm.org/docs/Passes.html#sroa-scalar-replacement-of-aggregates)
 *  	but it is more general. It is also similar to Bit-Tracking Dead Code Elimination BDCE.
 *  :note: The bit mask patterns and other special bit selection techniques should be recognized in advance and translated to
 *  	hwtHls.bitConcat and hwtHls.bitRangeGet
 */
class SlicesToIndependentVariablesPass: public llvm::PassInfoMixin<
		SlicesToIndependentVariablesPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
