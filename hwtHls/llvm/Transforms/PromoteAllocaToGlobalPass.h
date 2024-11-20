#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>



namespace hwtHls {

/*
 * Convert allocas to GlobalValue for constant or written only in initialization memories
 * * similar to AMDGPUPromoteAllocaImpl::tryPromoteAllocaToLDS
 *
 * */
class PromoteAllocaToGlobalPass: public llvm::PassInfoMixin<PromoteAllocaToGlobalPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);

};

}
