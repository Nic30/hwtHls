#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>

#include <hwtHls/llvm/Transforms/utils/writeCFGToDotFile.h>

namespace hwtHls {

class IntentionalCompilationInterupt: public std::runtime_error {
public:
	using std::runtime_error::runtime_error;
};

class DumpAndExitPass: public llvm::PassInfoMixin<DumpAndExitPass> {
	bool dumpFn;
	bool throwErrAndExit;
	std::optional<std::string> cfgDumpFileName;
public:
	explicit DumpAndExitPass(bool dumpFn, bool throwErrAndExit, std::optional<std::string> cfgDumpFileName={}) :
			dumpFn(dumpFn), throwErrAndExit(throwErrAndExit), cfgDumpFileName(cfgDumpFileName) {
	}

	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM) {
		if (dumpFn)
			F.dump();
		if (cfgDumpFileName.has_value()) {
			writeCFGToDotFile(F, cfgDumpFileName.value(), nullptr, nullptr);
		}
		if (throwErrAndExit)
			throw IntentionalCompilationInterupt(
					"IntentionalCompilationInterupt: " __FILE__);
		return llvm::PreservedAnalyses::all();
	}
};

}
