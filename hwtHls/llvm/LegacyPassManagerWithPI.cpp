#include <hwtHls/llvm/LegacyPassManagerWithPI.h>
#include <hwtHls/llvm/targets/Transforms/HwtHlsRunPassInstrumentationCallbacksPass.h>

namespace hwtHls {

void LegacyPassManagerWithPI::add(llvm::Pass *P) {
	llvm::legacy::PassManager::add(P);
	addPassCallbackFromPI(P);
}

void LegacyPassManagerWithPI::addPassCallbackFromPI(llvm::Pass *P) {
	std::string passName = "<unknown pass>";
	if (P) {
		passName = P->getPassName();
	}
	if (dynamic_cast<llvm::MachineFunctionPass*>(P)) {
		llvm::legacy::PassManager::add(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksMachineFunctionPass(
						PI, passName));
	} else if (dynamic_cast<llvm::FunctionPass*>(P)) {
		llvm::legacy::PassManager::add(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksFunctionPass(
						PI, passName));
	} else if (dynamic_cast<llvm::LoopPass*>(P)) {
		llvm::legacy::PassManager::add(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksLoopPass(PI,
						passName));
	} else if (dynamic_cast<llvm::ModulePass*>(P)) {
		llvm::legacy::PassManager::add(
				new hwtHls::HwtHlsRunPassInstrumentationCallbacksModulePass(PI,
						passName));
	} else {
		llvm::errs() << passName << "\n";
		llvm_unreachable("Unknown type of pass");
	}
}

}
