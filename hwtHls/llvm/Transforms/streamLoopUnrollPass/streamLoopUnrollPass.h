#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/// Loop unroll for loops which are dependent on some stream IO
class StreamLoopUnrollPass: public llvm::PassInfoMixin<StreamLoopUnrollPass> {

public:
	static llvm::StringRef name() {
		return "StreamLoopUnrollPass";
	}

	explicit StreamLoopUnrollPass() {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
