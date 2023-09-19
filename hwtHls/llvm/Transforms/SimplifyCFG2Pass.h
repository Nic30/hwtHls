#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Transforms/Utils/SimplifyCFGOptions.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>


namespace hwtHls {

/// same as original LLVM SimplifyCFGPass but with fixed merge of large switch instructions
// :attention: should be removed once https://github.com/llvm/llvm-project/issues/61391 is fixed
class SimplifyCFG2Pass : public llvm::SimplifyCFGPass {
	llvm::SimplifyCFGOptions Options;
public:
  using llvm::SimplifyCFGPass::SimplifyCFGPass;

  llvm::PreservedAnalyses run(llvm::Function &F, llvm::FunctionAnalysisManager &AM);

};

}

