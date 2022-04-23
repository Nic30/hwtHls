#include "genericFpgaTargetInfo.h"

#include <llvm/Support/TargetRegistry.h>

#include "genericFpgaMCTargetDesc.h"
#include "genericFpga.h"

using namespace llvm;

Target& getTheGenericFpgaTarget() {
	static Target TheGenericFpgaTarget;
	return TheGenericFpgaTarget;
}

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeGenericFpgaTargetInfo() {
	RegisterTarget<Triple::ArchType(Triple::LastArchType + 1), /*HasJIT=*/false> X(
			getTheGenericFpgaTarget(), "genericFpga",
			"hwtHls default generic FPGA", "fpga");
}
