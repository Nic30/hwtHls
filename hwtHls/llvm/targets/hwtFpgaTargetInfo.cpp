#include "hwtFpgaTargetInfo.h"

#include <llvm/MC/TargetRegistry.h>

#include "hwtFpgaMCTargetDesc.h"
#include "hwtFpga.h"

using namespace llvm;

Target& getTheHwtFpgaTarget() {
	static Target TheHwtFpgaTarget;
	return TheHwtFpgaTarget;
}

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeHwtFpgaTargetInfo() {
	RegisterTarget<Triple::ArchType(Triple::LastArchType + 1), /*HasJIT=*/false> X(
			getTheHwtFpgaTarget(), "hwtFpga",
			"hwtHls default generic FPGA", "fpga");
}