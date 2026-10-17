#pragma once

#include <llvm/ADT/SetVector.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/PassManager.h>

#include <hwtHls/llvm/Transforms/InstCombineABC1bLogicPass/llvmIrToAbcAig.h>

namespace hwtHls {

/**
 *  A pass which uses ABC to optimize 1b logic
 *
 *  :see: HlsNetlistToAbcAig, RtlNetlistToAbcAig
 *  :see: AbcAigToRtlNetlist, AbcAigToHlsNetlist
 */
class InstCombineABC1bLogicPass
	: public llvm::PassInfoMixin<InstCombineABC1bLogicPass> {
public:
	virtual void runOptScripts(LlvmIrToAbcAig &toAbc);

	virtual void
	findSelectedInstructions(llvm::Function &F,
							 llvm::SetVector<llvm::Instruction *> &selected,
							 llvm::SetVector<llvm::Value *> &inputs,
							 llvm::SetVector<llvm::Instruction *> &outputs);
	llvm::PreservedAnalyses run(llvm::Function &F,
								llvm::FunctionAnalysisManager &AM);
};

}
