#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  Overwrite all block names to be in format bb{n}
 *  This pass is useful when debugging IR with very long block names
 */
class OverwriteBlockNamesPass: public llvm::PassInfoMixin<
OverwriteBlockNamesPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
