#include <llvm/CodeGen/GlobalISel/InstructionSelector.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaRegisterBankInfo.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetSubtarget.h>
#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>

namespace hwtHls::HwtFpgaInstructionSelector {

llvm::ConstantInt* machineOperandTryGetConst(llvm::LLVMContext &Context,
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &MO);
void selectInstrArg(llvm::MachineFunction &MF, llvm::MachineInstrBuilder &MIB,
		llvm::MachineRegisterInfo &MRI, llvm::MachineOperand &MO);
void selectInstrArgs(llvm::MachineInstr &I, llvm::MachineInstrBuilder &MIB,
		bool firstIsDef);

}
