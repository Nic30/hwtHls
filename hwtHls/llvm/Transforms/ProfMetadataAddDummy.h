#pragma once

#include <llvm/IR/PassManager.h>

namespace hwtHls {

class ProfMetadataAddDummy: public llvm::PassInfoMixin<ProfMetadataAddDummy> {
public:
	static const std::string METADATA_NAME_DUMMY_PROF_MD;
	llvm::PreservedAnalyses run(llvm::Module &M, llvm::ModuleAnalysisManager&);
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
