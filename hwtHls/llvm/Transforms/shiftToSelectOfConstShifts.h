#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  A pass to rewrite non constant shifts with the select of constant shifts.
 */
class ShiftToSelectOfConstShiftPass: public llvm::PassInfoMixin<
		ShiftToSelectOfConstShiftPass> {

public:
	static llvm::StringRef name() {
		return "ExtractReplicationsPass";
	}

	explicit ShiftToSelectOfConstShiftPass() {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
