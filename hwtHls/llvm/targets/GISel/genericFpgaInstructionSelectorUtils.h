#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include "genericFpgaRegisterBankInfo.h"
#include "../genericFpgaTargetSubtarget.h"
#include "../genericFpgaTargetMachine.h"

namespace hwtHls::GenericFpgaInstructionSelector {

llvm::ConstantInt* machineOperandTryGetConst(llvm::LLVMContext &Context,
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &MO);
void selectInstrArg(llvm::MachineFunction &MF, llvm::MachineInstrBuilder &MIB,
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &MO);
void selectInstrArgs(llvm::MachineInstr &I, llvm::MachineInstrBuilder &MIB,
		bool firstIsDef);

}
