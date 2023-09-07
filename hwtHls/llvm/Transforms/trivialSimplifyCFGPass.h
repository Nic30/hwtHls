#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  Simplify trivial patterns in CFG
 *  * Remove empty basic block if has single successor and predecessor and may be replaced by predecessor in successor PHIs
 *  * Remove one operand PHIs and PHIs with all same values
 *
 *  :note: Primary purpose of this pass is to make code more readable for debugging. For real
 *  CFG simplification there is SimplifyCFG2Pass, SimplifyCFGPass.
 */
class TrivialSimplifyCFGPass: public llvm::PassInfoMixin<
TrivialSimplifyCFGPass> {

public:
	static llvm::StringRef name() {
		return "TrivialSimplifyCFGPass";
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
