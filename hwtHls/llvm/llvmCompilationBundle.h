#pragma once
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/Passes/PassBuilder.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/MC/TargetRegistry.h>

#include "llvmIrStrings.h"
#include "targets/Transforms/hwtFpgaToNetlist.h"
#include "targets/hwtFpgaTargetPassConfig.h"

namespace hwtHls {

/*
 * A container of all object which are required to compile the code with LLVM.
 * */
class LlvmCompilationBundle {
public:
	llvm::LLVMContext ctx;
	LLVMStringContext strCtx;
	std::unique_ptr<llvm::Module> mod;
	llvm::IRBuilder<> builder;
	llvm::Function *main;
	llvm::PassBuilder PB; // for IR passes
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

	LlvmCompilationBundle(const std::string &moduleName);
	void addLlvmCliArgOccurence(const std::string & OptionName, unsigned pos, const std::string & ArgName, const std::string & ArgValue);
	// for arg description see HwtFpgaTargetPassConfig
	// :param combinerCallback: is an optional callback function called during last state of
	//        instruction combining
	void runOpt(hwtHls::HwtFpgaToNetlist::ConvesionFnT toNetlistConversionFn);
	llvm::MachineFunction* getMachineFunction(llvm::Function &fn);

	llvm::MachineModuleInfo* getMachineModuleInfo();

	void _addVectorPasses(llvm::OptimizationLevel Level,
			llvm::FunctionPassManager &FPM, bool IsFullLTO);
	// for arg description see HwtFpgaTargetPassConfig
	void _addMachineCodegenPasses(
			hwtHls::HwtFpgaToNetlist::ConvesionFnT &toNetlistConversionFn);

	llvm::Function& _testSlicesToIndependentVariablesPass();
	llvm::Function& _testBitwidthReductionPass();
	llvm::Function& _testSlicesMergePass();
	llvm::Function& _testRewriteExtractOnMergeValues();
	llvm::Function& _testFunctionPass(
			std::function<void(llvm::FunctionPassManager&)> addPasses);
	void _testEarlyIfConverter();
};



}
