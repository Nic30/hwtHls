#pragma once
#include <llvm/CodeGen/RegisterBank.h>
#include <llvm/CodeGen/RegisterBankInfo.h>

namespace llvm {

class GenericFpgaRegisterBankInfo: public llvm::RegisterBankInfo {
public:
	GenericFpgaRegisterBankInfo();
	const InstructionMapping&
	getInstrMapping(const MachineInstr &MI) const override;
	const RegisterBank&
	getRegBankFromRegClass(const TargetRegisterClass &RC, LLT Ty) const
			override;
};

extern GenericFpgaRegisterBankInfo genericFpgaRegisterBankInfo;

}
