#pragma once
#include <llvm/Support/Compiler.h>

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeHwtFpgaTarget();
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeHwtFpgaTargetInfo();
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeHwtFpgaTargetMC();

inline void hwtFpgaTargetInitialize() {
	LLVMInitializeHwtFpgaTarget();
	LLVMInitializeHwtFpgaTargetInfo();
	LLVMInitializeHwtFpgaTargetMC();

}
