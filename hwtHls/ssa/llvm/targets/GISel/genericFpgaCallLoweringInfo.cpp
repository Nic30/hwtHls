#include "genericFpgaCallLoweringInfo.h"
#include "genericFpgaTargetLowering.h"

using namespace llvm;

namespace llvm {

GenericFpgaCallLowering::GenericFpgaCallLowering(
		const llvm::GenericFpgaTargetLowering &TLI) :
		llvm::CallLowering(&TLI) {
}

bool GenericFpgaCallLowering::lowerReturn(MachineIRBuilder &MIRBuilder,
		const Value *Val, ArrayRef<Register> VRegs,
		FunctionLoweringInfo &FLI) const {

	//MachineInstrBuilder Ret = MIRBuilder.buildInstrNoInsert(GenericFpga::PseudoRET);
	//
	//if (Val != nullptr) {
	//  return false;
	//}
	//MIRBuilder.insertInstr(Ret);
	return true;
}

bool GenericFpgaCallLowering::lowerFormalArguments(MachineIRBuilder &MIRBuilder,
		const Function &F, ArrayRef<ArrayRef<Register>> VRegs,
		FunctionLoweringInfo &FLI) const {

	//if (F.arg_empty())
	//	return true;

	return false;
}

bool GenericFpgaCallLowering::lowerCall(MachineIRBuilder &MIRBuilder,
		CallLoweringInfo &Info) const {
	return false;
}

}
