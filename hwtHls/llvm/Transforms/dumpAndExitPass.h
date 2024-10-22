#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>
#include <llvm/IR/Verifier.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>


namespace hwtHls {

class IntentionalCompilationInterupt: public std::runtime_error {
public:
	using std::runtime_error::runtime_error;
};

class DumpAndExitPass: public llvm::PassInfoMixin<DumpAndExitPass> {
	bool dumpFn;
	bool throwErrAndExit;
	bool verify;
	std::optional<std::string> cfgDumpFileName;
	bool dumpModule;
public:
	explicit DumpAndExitPass(bool dumpFn, bool throwErrAndExit, std::optional<std::string> cfgDumpFileName={}, bool verify=false, bool dumpModule=false) :
			dumpFn(dumpFn), throwErrAndExit(throwErrAndExit), verify(verify), cfgDumpFileName(cfgDumpFileName), dumpModule(dumpModule) {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		if (dumpFn) {
			F.dump();
		}
		if (dumpModule)
			F.getParent()->dump();

		if (cfgDumpFileName.has_value()) {
			writeCFGToDotFile(F, cfgDumpFileName.value(), AM);
		}
		if (verify) {
			if(llvm::verifyModule(*F.getParent(), &llvm::dbgs())) {
				llvm::dbgs() << "Module is broken\n";
			} else {
				llvm::dbgs() << "Module is valid\n";
			}
		}
		if (throwErrAndExit)
			throw IntentionalCompilationInterupt(
					"IntentionalCompilationInterupt: " __FILE__);
		return llvm::PreservedAnalyses::all();
	}
};

}
