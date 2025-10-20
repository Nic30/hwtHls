#pragma once

#include <set>
#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 * Strip @llvm.assume and alike instructions
 */
class StripAssumePass: public llvm::PassInfoMixin<StripAssumePass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}
