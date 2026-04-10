#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaRegisterBankInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetSubtarget.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

namespace llvm {
InstructionSelector*
createHwtFpgaInstructionSelector(const HwtFpgaTargetMachine &TM,
		const HwtFpgaTargetSubtarget &Subtarget, const HwtFpgaRegisterBankInfo &RBI);
}
