#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include "genericFpgaRegisterBankInfo.h"
#include "../genericFpgaTargetSubtarget.h"
#include "../genericFpgaTargetMachine.h"

namespace llvm {
InstructionSelector*
createGenericFpgaInstructionSelector(const GenericFpgaTargetMachine &TM,
		GenericFpgaTargetSubtarget &Subtarget, GenericFpgaRegisterBankInfo &RBI);
}
