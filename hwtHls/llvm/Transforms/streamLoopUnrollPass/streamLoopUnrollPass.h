#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/// Loop unroll for loops which are dependent on some stream IO
class StreamLoopUnrollPass: public llvm::PassInfoMixin<StreamLoopUnrollPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
