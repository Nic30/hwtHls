#pragma once

#include <llvm/CodeGen/TargetPassConfig.h>
#include "genericFpgaTargetMachine.h"
#include "Transforms/genericFpgaToNetlist.h"

namespace llvm {

/// GenericFpga Code Generator Pass Configuration Options.
class GenericFpgaTargetPassConfig: public llvm::TargetPassConfig {
public:
	// callback function which is used to translate final MIR to Python objects
	// the callback is used because the translation must be performed until exit
	// from translation pipeline because after exit the objects would deallocate
	hwtHls::GenericFpgaToNetlist::ConvesionFnT * toNetlistConversionFn;

	GenericFpgaTargetPassConfig(GenericFpgaTargetMachine &TM,
			llvm::PassManagerBase &PM) :
			llvm::TargetPassConfig(TM, PM), toNetlistConversionFn(nullptr) {
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
