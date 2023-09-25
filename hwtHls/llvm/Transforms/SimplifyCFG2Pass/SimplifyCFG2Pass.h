#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Transforms/Utils/SimplifyCFGOptions.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>

namespace hwtHls {

/// same as original LLVM SimplifyCFGPass but with fixed merge of large switch instructions
// :attention: should be removed once https://github.com/llvm/llvm-project/issues/61391 is fixed
class SimplifyCFG2Pass: public llvm::SimplifyCFGPass {
	llvm::SimplifyCFGOptions Options; // [copied] copied from llvm base class because of SimplifyCFG private Options which can not be accessed through inheritance

public:
	SimplifyCFG2Pass();
	/// Construct a pass with optional optimizations.
	SimplifyCFG2Pass(const llvm::SimplifyCFGOptions &PassOptions);

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}

