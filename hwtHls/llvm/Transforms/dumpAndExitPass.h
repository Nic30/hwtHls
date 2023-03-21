#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>

namespace hwtHls {

class IntentionalCompilationInterupt: std::exception {};
class DumpAndExitPass: public llvm::PassInfoMixin<DumpAndExitPass> {
	bool dumpFn;
	bool throwErrAndExit;
public:
	explicit DumpAndExitPass(bool dumpFn, bool throwErrAndExit): dumpFn(dumpFn), throwErrAndExit(throwErrAndExit) {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		if (dumpFn)
			F.dump();
		if (throwErrAndExit)
			throw IntentionalCompilationInterupt();
		// Mark all the analyses that instcombine updates as preserved.
		llvm::PreservedAnalyses PA;
		PA.preserveSet<llvm::CFGAnalyses>();
		PA.preserve<llvm::AAManager>();
		PA.preserve<llvm::BasicAA>();
		PA.preserve<llvm::GlobalsAA>();
		return PA;
	}
};

}
