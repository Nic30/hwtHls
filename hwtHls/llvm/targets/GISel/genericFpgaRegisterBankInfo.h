#pragma once
#include <llvm/CodeGen/GlobalISel/RegisterBankInfo.h>
#include <llvm/CodeGen/GlobalISel/RegisterBank.h>

namespace llvm {

class GenericFpgaRegisterBankInfo: public llvm::RegisterBankInfo {
public:
	RegisterBank AnyRegBank;
	//RegisterBank ControlRegBank;

	GenericFpgaRegisterBankInfo();
	const InstructionMapping&
	getInstrMapping(const MachineInstr &MI) const override;
	const RegisterBank&
	getRegBankFromRegClass(const TargetRegisterClass &RC, LLT Ty) const
			override;

};

extern GenericFpgaRegisterBankInfo genericFpgaRegisterBankInfo;

}
