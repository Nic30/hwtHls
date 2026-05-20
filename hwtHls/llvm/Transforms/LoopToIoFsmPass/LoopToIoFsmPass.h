#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/// Cut cfg on IO instructions and build a loop which begins with a single load/ ends with single store
//  and have transition between segments encoded inside of FSM state variable instead of original CFG. 
class LoopToIoFsmPass: public llvm::PassInfoMixin<LoopToIoFsmPass> {
public:
	static const std::string METADATA_NAME_io;
	static const std::string METADATA_NAME_followup;
	
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
