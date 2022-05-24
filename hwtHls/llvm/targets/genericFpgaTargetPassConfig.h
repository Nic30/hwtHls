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
	bool addInstSelector() override; // used only to raise error
	void addStraightLineScalarOptimizationPasses();
	void addIRPasses() override;
	void addCodeGenPrepare() override;
	bool addPreISel() override;
	bool addIRTranslator() override;
	void addPreLegalizeMachineIR() override;
	bool addLegalizeMachineIR() override;
	bool addRegBankSelect() override;
	bool addGlobalInstructionSelect() override;
	void addPreSched2() override;
	FunctionPass* createTargetRegisterAllocator(bool Optimized) override;
	bool addILPOpts() override; // added from addMachineSSAOptimization which is added from addMachinePasses
	void addOptimizedRegAlloc() override;
	void addMachinePasses() override;
	// No reg alloc
	//bool addRegAssignAndRewriteFast() override {
	//	return false;
	//}
	//bool addRegAssignAndRewriteOptimized() override {
	//	return false;
	//}
};

}
