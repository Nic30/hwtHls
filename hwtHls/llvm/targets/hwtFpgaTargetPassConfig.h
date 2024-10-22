#pragma once

#include <llvm/CodeGen/TargetPassConfig.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>
#include <hwtHls/llvm/targets/Transforms/hwtFpgaToNetlist.h>

namespace llvm {

/// HwtFpga Code Generator Pass Configuration Options.
class HwtFpgaTargetPassConfig: public llvm::TargetPassConfig {
public:
	// callback function which is used to translate final MIR to Python objects
	// the callback is used because the translation must be performed until exit
	// from translation pipeline because after exit the objects would deallocate
	hwtHls::HwtFpgaToNetlist::ConvesionFnT * toNetlistConversionFn;

	HwtFpgaTargetPassConfig(HwtFpgaTargetMachine &TM,
			llvm::PassManagerBase &PM) :
			llvm::TargetPassConfig(TM, PM), toNetlistConversionFn(nullptr) {
	}
	HwtFpgaTargetMachine& getHwtFpgaTargetMachine() const {
		return getTM<HwtFpgaTargetMachine>();
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
	void _addBlockReductionPasses();
	std::unique_ptr<CSEConfigBase> getCSEConfig() const override;

	// No reg alloc
	//bool addRegAssignAndRewriteFast() override {
	//	return false;
	//}
	//bool addRegAssignAndRewriteOptimized() override {
	//	return false;
	//}
	// exposed addPass method for testing purposes
	AnalysisID _testAddPass(AnalysisID PassID);
	void _testAddPass(Pass *P);

};

}
