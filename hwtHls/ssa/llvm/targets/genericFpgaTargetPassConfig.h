#pragma once

#include <llvm/CodeGen/TargetPassConfig.h>
#include "genericFpgaTargetMachine.h"

namespace llvm {

/// GenericFpga Code Generator Pass Configuration Options.
class GenericFpgaTargetPassConfig: public llvm::TargetPassConfig {
public:
	GenericFpgaTargetPassConfig(GenericFpgaTargetMachine &TM,
			llvm::PassManagerBase &PM) :
			llvm::TargetPassConfig(TM, PM) {
	}

	GenericFpgaTargetMachine& getGenericFpgaTargetMachine() const {
		return getTM<GenericFpgaTargetMachine>();
	}
	/// which converts from LLVM code to machine instructions.
	bool addInstSelector() override;
	void addCodeGenPrepare() override;
	void addMachinePasses() override;
};

}
