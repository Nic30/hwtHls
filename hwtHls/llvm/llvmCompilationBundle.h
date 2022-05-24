#pragma once
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/CodeGen/MachineFunction.h>
#include <llvm/CodeGen/MachineModuleInfo.h>
#include <llvm/Passes/PassBuilder.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/MC/TargetRegistry.h>

#include "llvmIrStrings.h"
#include "targets/Transforms/genericFpgaToNetlist.h"

namespace hwtHls {

/*
 * A container of all object which are required to compile the code with LLVM.
 * */
class LlvmCompilationBundle {
public:
	llvm::LLVMContext ctx;
	LLVMStringContext strCtx;
	llvm::Module mod;
	llvm::IRBuilder<> builder;
	llvm::Function *main;
	llvm::PassBuilder PB; // for IR passes
	llvm::legacy::PassManager PM; // for machine code generator
	const llvm::Target *Target;
	llvm::OptimizationLevel Level;
	bool EnableO3NonTrivialUnswitching;
	bool EnableGVNHoist;
	bool EnableGVNSink;
	llvm::TargetMachine *TM;
	llvm::PipelineTuningOptions PTO;
	llvm::MachineModuleInfoWrapperPass *MMIWP;

	LlvmCompilationBundle(const std::string &moduleName);
	// :param combinerCallback: is an optional callback function called during last state of
	//        instruction combining
	void runOpt(hwtHls::GenericFpgaToNetlist::ConvesionFnT toNetlist);
	llvm::MachineFunction* getMachineFunction(llvm::Function &fn);
};

}
