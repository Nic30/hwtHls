#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  A pass to lower AllocaInst marked with hwtHls.tmp.alloca using llvm::PromoteMemToReg.
 */
class TmpAllocaLoweringPass: public llvm::PassInfoMixin<TmpAllocaLoweringPass> {
public:
	static const std::string HwtHlsTmpAllocaName;
	static const std::string HwtHlsTmpPropagateNoSplitName;
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
