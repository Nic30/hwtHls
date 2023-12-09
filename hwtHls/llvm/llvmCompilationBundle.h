#pragma once
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/Passes/PassBuilder.h>
#include <llvm/Passes/StandardInstrumentations.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/MC/TargetRegistry.h>

#include <hwtHls/llvm/llvmIrStrings.h>
#include <hwtHls/llvm/targets/Transforms/hwtFpgaToNetlist.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetPassConfig.h>

namespace hwtHls {

/*
 * A container of all object which are required to compile the code with LLVM.
 * */
class LlvmCompilationBundle {
public:
	llvm::LLVMContext ctx;
	LLVMStringContext strCtx;
	llvm::Module* module;
	llvm::IRBuilder<> builder;
	llvm::Function *main;
	std::unique_ptr<llvm::PassBuilder> PB; // for IR passes
	llvm::legacy::PassManager PM; // for machine code generator
	const llvm::Target *Target;
	llvm::HwtFpgaTargetPassConfig *TPC;
	llvm::OptimizationLevel Level;
	bool EnableO3NonTrivialUnswitching;
	bool EnableGVNHoist;
	bool EnableGVNSink;
	llvm::TargetMachine *TM;
	llvm::PipelineTuningOptions PTO;
	llvm::MachineModuleInfoWrapperPass *MMIWP;
	bool VerifyEachPass;
	enum class DebugLogging {
		None, Normal, Verbose, Quiet
	};
	DebugLogging DebugPM;
	llvm::PassInstrumentationCallbacks PIC;
	llvm::PrintPassOptions PrintPassOpts;
	static const std::string TargetTriple;
	static const std::string CPU;
	static const std::string Features;

	LlvmCompilationBundle(const std::string &moduleName);
	void _initPassBuilder();

	void addLlvmCliArgOccurence(const std::string &OptionName, unsigned pos,
			const std::string &ArgName, const std::string &ArgValue);
	// for arg description see HwtFpgaTargetPassConfig
	// :param combinerCallback: is an optional callback function called during last state of
	//        instruction combining
	void runOpt(hwtHls::HwtFpgaToNetlist::ConvesionFnT toNetlistConversionFn);
	llvm::MachineFunction* getMachineFunction(llvm::Function &fn);

	llvm::MachineModuleInfo* getMachineModuleInfo();

	void _addInitialNormalizationPasses(llvm::FunctionPassManager &FPM);
	void _addStreamOperationLoweringPasses(llvm::FunctionPassManager &FPM);
	void _addLoopPasses(llvm::FunctionPassManager &FPM);
	void _addVectorPasses(llvm::OptimizationLevel Level,
			llvm::FunctionPassManager &FPM, bool IsFullLTO);
	void _addInstrCombinePasses(llvm::FunctionPassManager &FPM);
	// for arg description see HwtFpgaTargetPassConfig
	void _addMachineCodegenPasses(
			hwtHls::HwtFpgaToNetlist::ConvesionFnT &toNetlistConversionFn);
	void _addCommonPasses(llvm::FunctionPassManager &FPM);

	llvm::Function& _testSlicesToIndependentVariablesPass();
	llvm::Function& _testBitwidthReductionPass();
	llvm::Function& _testSlicesMergePass();
	llvm::Function& _testRewriteExtractOnMergeValues();
	llvm::Function& _testFunctionPass(
			std::function<void(llvm::FunctionPassManager&)> addPasses);
	void _testMachineFunctionPass(
			std::function<void(llvm::HwtFpgaTargetPassConfig&)> addPasses);

	void _testEarlyIfConverter();
	void _testVRegIfConverter();
	// _testVRegIfConverter which has input in LLVM IR
	// (which is then translated to MIR which is then processed by VRegIfConverter)
	void _testVRegIfConverterForIr();
};

}
