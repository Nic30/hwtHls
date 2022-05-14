#pragma once
#include <llvm/Support/Compiler.h>

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeGenericFpgaTarget();
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeGenericFpgaTargetInfo();
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeGenericFpgaTargetMC();

inline void genericFpgaTargetInitialize() {
	LLVMInitializeGenericFpgaTarget();
	LLVMInitializeGenericFpgaTargetInfo();
	LLVMInitializeGenericFpgaTargetMC();

}
