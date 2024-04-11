#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Target/TargetMachine.h>

namespace hwtHls {

class ReconfigureHwtFpgaTTIPass: public llvm::PassInfoMixin<
		ReconfigureHwtFpgaTTIPass> {
	llvm::TargetMachine *TM;
	std::optional<bool> AllowVolatileMemOpDuplication;
public:
	explicit ReconfigureHwtFpgaTTIPass(llvm::TargetMachine *_TM,
			std::optional<bool> _AllowVolatileMemOpDuplication = { }) :
			TM(_TM), AllowVolatileMemOpDuplication(
					_AllowVolatileMemOpDuplication) {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}

