#include <llvm/Pass.h>
#include <llvm/Analysis/LoopPass.h>
#include <llvm/IR/PassInstrumentation.h>
#include <llvm/CodeGen/MachineFunctionPass.h>

namespace hwtHls {

class HwtHlsRunPassInstrumentationCallbacksFunctionPass: public llvm::FunctionPass {
public:
	static char ID; // Pass identification, replacement for typeid
	llvm::PassInstrumentation &PI;
	std::string PreviousPassName;

	HwtHlsRunPassInstrumentationCallbacksFunctionPass(
			llvm::PassInstrumentation &PI, std::string PreviousPassName) :
			llvm::FunctionPass(ID), PI(PI), PreviousPassName(PreviousPassName) {
	}
	bool runOnFunction(llvm::Function &F) override;
	llvm::StringRef getPassName() const override {
		return "HwtHls run PassInstrumentationCallbacks pass";
	}
};

class HwtHlsRunPassInstrumentationCallbacksLoopPass: public llvm::LoopPass {
public:
	static char ID; // Pass identification, replacement for typeid
	llvm::PassInstrumentation &PI;
	std::string PreviousPassName;

	HwtHlsRunPassInstrumentationCallbacksLoopPass(
			llvm::PassInstrumentation &PI, std::string PreviousPassName) :
			llvm::LoopPass(ID), PI(PI), PreviousPassName(PreviousPassName) {
	}
	bool runOnLoop(llvm::Loop *L, llvm::LPPassManager &LPM) override;

	llvm::StringRef getPassName() const override {
		return "HwtHls run PassInstrumentationCallbacks pass";
	}
};

class HwtHlsRunPassInstrumentationCallbacksMachineFunctionPass: public llvm::MachineFunctionPass {
public:
	static char ID; // Pass identification, replacement for typeid
	llvm::PassInstrumentation &PI;
	std::string PreviousPassName;

	HwtHlsRunPassInstrumentationCallbacksMachineFunctionPass(
			llvm::PassInstrumentation &PI, std::string PreviousPassName) :
			llvm::MachineFunctionPass(ID), PI(PI), PreviousPassName(
					PreviousPassName) {
	}
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;

	llvm::StringRef getPassName() const override {
		return "HwtHls run PassInstrumentationCallbacks pass";
	}
};

}
