#pragma once

#include <llvm/CodeGen/CallingConvLower.h>
#include <llvm/CodeGen/GlobalISel/CallLowering.h>
#include <llvm/CodeGen/ValueTypes.h>

namespace llvm {

class HwtFpgaTargetLowering;

class HwtFpgaCallLowering: public llvm::CallLowering {

public:
	HwtFpgaCallLowering(const HwtFpgaTargetLowering &TLI);

	bool lowerReturn(llvm::MachineIRBuilder &MIRBuiler, const llvm::Value *Val,
			llvm::ArrayRef<llvm::Register> VRegs,
			llvm::FunctionLoweringInfo &FLI) const override;

	bool lowerFormalArguments(llvm::MachineIRBuilder &MIRBuilder,
			const llvm::Function &F,
			llvm::ArrayRef<llvm::ArrayRef<llvm::Register>> VRegs,
			llvm::FunctionLoweringInfo &FLI) const override;

	bool lowerCall(llvm::MachineIRBuilder &MIRBuilder,
			CallLoweringInfo &Info) const override;
	bool canLowerReturn(MachineFunction &MF, CallingConv::ID CallConv,
			SmallVectorImpl<BaseArgInfo> &Outs, bool IsVarArg) const override;
};

}
