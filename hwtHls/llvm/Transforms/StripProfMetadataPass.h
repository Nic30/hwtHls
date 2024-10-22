#pragma once

#include <llvm/IR/PassManager.h>

namespace llvm {
class Module;
class Function;
}

namespace hwtHls {

//===----------------------------------------------------------------------===//
//
// This pass loops over all of the functions in the input module and
// removes prof metadata from them
//
//===----------------------------------------------------------------------===//
class StripProfMetadataPass: public llvm::PassInfoMixin<StripProfMetadataPass> {
public:
	llvm::PreservedAnalyses run(llvm::Module &M, llvm::ModuleAnalysisManager&);
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
