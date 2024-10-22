#pragma once

#include <llvm/CodeGen/MachineFunctionPass.h>

namespace llvm {
class HwtFpgaTargetPassConfig;
}

namespace hwtHls {

/*
 * Resolve minimal bitwidth for individual registers.
 *
 * :note: LLVM SPIRV getMachineInstrType stores type in metada operand
 * 	this sets LLT of each register
 * */
class HwtFpgaRegisterBitWidth: public llvm::MachineFunctionPass {
public:
	static char ID;
	HwtFpgaRegisterBitWidth();
	void getAnalysisUsage(llvm::AnalysisUsage &AU) const override;
	bool runOnMachineFunction(llvm::MachineFunction &MF) override;
	llvm::StringRef getPassName() const override {
		return "HwtFpgaRegisterBitWidth";
	}
};


}
