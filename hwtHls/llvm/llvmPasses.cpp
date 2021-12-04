#include "llvm/ADT/APInt.h"
#include "llvm/ADT/APSInt.h"
#include "llvm/ADT/STLExtras.h"
#include "llvm/IR/BasicBlock.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/DerivedTypes.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/LLVMContext.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Type.h"
#include "llvm/IR/Verifier.h"
//#include "llvm/IR/PassManager.h"
//#include "llvm/IR/LegacyPassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Pass.h"

//#include "llvm/Transforms/IPO/PassManagerBuilder.h"
#include "llvm/Transforms/InstCombine/InstCombine.h"
#include "llvm/Transforms/AggressiveInstCombine/AggressiveInstCombine.h"
#include "llvm/Transforms/Scalar.h"
#include "llvm/Transforms/Scalar/Reassociate.h"
#include "llvm/Transforms/Scalar/NewGVN.h"
#include "llvm/Transforms/Scalar/DCE.h"
#include "llvm/Transforms/Scalar/SCCP.h"

#include "llvm/Transforms/Scalar/SimplifyCFG.h"

#include "llvm/Transforms/Utils.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <string>
#include <vector>
#include <iostream>

#include <pybind11/functional.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

#include "llvmPasses.h"
namespace py = pybind11;

//void initializePassPipeline(llvm::legacy::FunctionPassManager *FPA) {
//	// Promote allocas to registers.
//	//functionPassManager->add(llvm::createPromoteMemoryToRegisterPass());
//	// Do simple "peephole" optimizations
//	FPA->add(llvm::createInstructionCombiningPass());
//	// Reassociate expressions.
//	FPA->add(llvm::createReassociatePass());
//	// Eliminate Common SubExpressions.
//	FPA->add(llvm::createGVNPass());
//	// Simplify the control flow graph (deleting unreachable blocks etc).
//	FPA->add(llvm::createCFGSimplificationPass());
//
//	FPA->doInitialization();
//}
// // [todo] once available in debian repo https://vpn.yonyou.com/prx/000/https/llvm.org/docs/NewPassManager.html
// auto FPA = std::make_unique<llvm::legacy::FunctionPassManager>(mod.get());
// initializePassPipeline(FPA.get());

void runOpt(llvm::Function & fn) {
	// https://stackoverflow.com/questions/34255383/llvm-3-5-passmanager-vs-legacypassmanager
	// https://stackoverflow.com/questions/51934964/function-optimization-pass

	llvm::PassBuilder PB;
	//llvm::FunctionAnalysisManager FAM;
	//PB.registerFunctionAnalyses(FAM);
	////llvm::FunctionPassManager FPM;
	//llvm::FunctionPassManager FPM = PB.buildFunctionSimplificationPipeline(
	//		llvm::PassBuilder::OptimizationLevel::O3, llvm::ThinOrFullLTOPhase::None);

	auto loop_manager = llvm::LoopAnalysisManager{};
	auto cgscc_manager = llvm::CGSCCAnalysisManager{};
	auto mod_manager = llvm::ModuleAnalysisManager{};
	auto FAM = llvm::FunctionAnalysisManager{};

	PB.registerModuleAnalyses(mod_manager);
	PB.registerCGSCCAnalyses(cgscc_manager);
	PB.registerFunctionAnalyses(FAM);
	PB.registerLoopAnalyses(loop_manager);

	PB.crossRegisterProxies(loop_manager, FAM, cgscc_manager, mod_manager);
	llvm::FunctionPassManager FPM;

	//llvm::FunctionPassManager FPM = PB.buildFunctionSimplificationPipeline(
	//		llvm::PassBuilder::OptimizationLevel::O0,
	//		//llvm::PassBuilder::ThinLTOPhase::None,
	//		llvm::ThinOrFullLTOPhase::None);

	// Promote allocas to registers.
	//Builder.addPass(llvm::PromoteMemoryToRegisterPass());
	// Do simple "peephole" optimizations
	//FPM.addPass(llvm::InstCombinePass());
	FPM.addPass(llvm::DCEPass());
	FPM.addPass(llvm::SCCPPass());
	//FPM.addPass(llvm::AggressiveInstCombinePass());
	//// Reassociate expressions.
	FPM.addPass(llvm::ReassociatePass());
	////// Eliminate Common SubExpressions.
	FPM.addPass(llvm::NewGVNPass());
	////// Simplify the control flow graph (deleting unreachable blocks etc).
	FPM.addPass(llvm::SimplifyCFGPass());


	// if (PB.parsePassPipeline(FPM, "pipeline0"))
	// 	std::cout << "###########err" << std::endl;



	FPM.run(fn, FAM);
}

