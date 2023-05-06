#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include "hwtFpgaRegisterBankInfo.h"
#include "../hwtFpgaTargetSubtarget.h"
#include "../hwtFpgaTargetMachine.h"

namespace llvm {
InstructionSelector*
createHwtFpgaInstructionSelector(const HwtFpgaTargetMachine &TM,
		HwtFpgaTargetSubtarget &Subtarget, HwtFpgaRegisterBankInfo &RBI);
}
