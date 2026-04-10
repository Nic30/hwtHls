#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/Module.h>
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
	bool cfgOnly;
public:
	explicit DumpAndExitPass(bool dumpFn, bool throwErrAndExit, std::optional<std::string> cfgDumpFileName={},
						     bool verify=false, bool dumpModule=false, bool cfgOnly=false) :
			dumpFn(dumpFn), throwErrAndExit(throwErrAndExit), verify(verify),
			cfgDumpFileName(cfgDumpFileName), dumpModule(dumpModule), cfgOnly(cfgOnly) {
			if (cfgOnly) {
				assert(cfgDumpFileName.has_value() && "cfgOnly option is intend to be used with cfgDumpFileName");
			}
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		if (dumpFn) {
			F.dump();
		}
		if (dumpModule)
			F.getParent()->dump();

		if (cfgDumpFileName.has_value()) {
			writeCFGToDotFile(F, cfgDumpFileName.value(), AM, false, cfgOnly);
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
