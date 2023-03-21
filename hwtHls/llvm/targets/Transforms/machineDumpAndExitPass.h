#pragma once
#include <llvm/CodeGen/MachineFunctionPass.h>
#include <llvm/CodeGen/MachineLoopInfo.h>

namespace hwtHls {

class MachineDumpAndExitPass: public llvm::MachineFunctionPass {
	bool dumpFn;
	bool throwErrAndExit;
public:
	static char ID;
	explicit MachineDumpAndExitPass(bool dumpFn, bool throwErrAndExit) :
			llvm::MachineFunctionPass(ID), dumpFn(dumpFn), throwErrAndExit(throwErrAndExit) {
	}
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "MachineDumpAndExitPass";
	}
};

}
