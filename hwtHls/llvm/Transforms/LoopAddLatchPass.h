#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  For loops with have jump from body back to body add a new latch block and move loop id there.
 *  This is useful when other transformations are expecting loops with latch
 *
 *  :note: llvm::LoopSimplifyPass will not add latch for 1 block loops (which is functionality of this pass)
 */
class LoopAddLatchPass: public llvm::PassInfoMixin<LoopAddLatchPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
