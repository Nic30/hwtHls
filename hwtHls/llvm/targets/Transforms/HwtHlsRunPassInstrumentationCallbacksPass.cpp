#include <hwtHls/llvm/targets/Transforms/HwtHlsRunPassInstrumentationCallbacksPass.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

struct PassMockup {
	std::string &_name;
	PassMockup(std::string &name) :
			_name(name) {
	}
	std::string name() const {
		return _name;
	}
};

bool HwtHlsRunPassInstrumentationCallbacksFunctionPass::runOnFunction(
		llvm::Function &F) {
	auto PA = llvm::PreservedAnalyses::all();
	PassMockup Pass(PreviousPassName);
	PI.runAfterPass(Pass, F, PA);
	return false;
}

char HwtHlsRunPassInstrumentationCallbacksFunctionPass::ID = 0;

bool HwtHlsRunPassInstrumentationCallbacksLoopPass::runOnLoop(llvm::Loop *L,
		llvm::LPPassManager &LPM) {
	auto PA = llvm::PreservedAnalyses::all();
	PassMockup Pass(PreviousPassName);
	PI.runAfterPass(Pass, *L, PA);
	return false;
}

char HwtHlsRunPassInstrumentationCallbacksLoopPass::ID = 0;

bool HwtHlsRunPassInstrumentationCallbacksMachineFunctionPass::runOnMachineFunction(
		llvm::MachineFunction &MF) {
	auto PA = llvm::PreservedAnalyses::all();
	PassMockup Pass(PreviousPassName);
	PI.runAfterPass(Pass, MF, PA);
	return false;
}

char HwtHlsRunPassInstrumentationCallbacksMachineFunctionPass::ID = 0;

}
