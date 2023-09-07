#pragma once
#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {


/*
Same as :class:`hwtHls.StreamReadLoweringPass` just for writes.

The output word is written if the word is completed and it is know if this word is last or not.
Or if data for next word are stacked or on end of frame marker.
*/
class StreamWriteLoweringPass: public llvm::PassInfoMixin<StreamWriteLoweringPass> {

public:
	static llvm::StringRef name() {
		return "StreamWriteLoweringPass";
	}

	explicit StreamWriteLoweringPass() {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
