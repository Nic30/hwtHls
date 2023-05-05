#pragma once

#include <llvm/CodeGen/MachineFunctionPass.h>

namespace llvm {
class GenericFpgaTargetPassConfig;
}

namespace hwtHls {

/*
 * Resolve minimal bitwidth for individual registers.
 * */
class GenFpgaRegisterBitWidth: public llvm::MachineFunctionPass {
public:
	static char ID;
	GenFpgaRegisterBitWidth();
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "GenFpgaRegisterBitWidth";
	}
};


}
