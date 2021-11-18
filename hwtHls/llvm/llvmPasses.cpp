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
#include "llvm/IR/LegacyPassManager.h"
//#include "llvm/Passes/PassBuilder.h"

#include "llvm/Transforms/InstCombine/InstCombine.h"
#include "llvm/Transforms/Scalar.h"
#include "llvm/Transforms/Scalar/GVN.h"
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

#include "llvmPasses.h"

void initializePassPipeline(llvm::legacy::FunctionPassManager *FPA) {
	// Promote allocas to registers.
	//functionPassManager->add(llvm::createPromoteMemoryToRegisterPass());
	// Do simple "peephole" optimizations
	FPA->add(llvm::createInstructionCombiningPass());
	// Reassociate expressions.
	FPA->add(llvm::createReassociatePass());
	// Eliminate Common SubExpressions.
	FPA->add(llvm::createGVNPass());
	// Simplify the control flow graph (deleting unreachable blocks etc).
	FPA->add(llvm::createCFGSimplificationPass());

	FPA->doInitialization();
}
// // [todo] once available in debian repo https://vpn.yonyou.com/prx/000/https/llvm.org/docs/NewPassManager.html
// auto FPA = std::make_unique<llvm::legacy::FunctionPassManager>(mod.get());
// initializePassPipeline(FPA.get());
