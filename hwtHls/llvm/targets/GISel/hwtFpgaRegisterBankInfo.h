#pragma once
#include <llvm/CodeGen/RegisterBank.h>
#include <llvm/CodeGen/RegisterBankInfo.h>

namespace llvm {

class HwtFpgaRegisterBankInfo: public llvm::RegisterBankInfo {
public:
	HwtFpgaRegisterBankInfo();
	const InstructionMapping&
	getInstrMapping(const MachineInstr &MI) const override;
	const RegisterBank&
	getRegBankFromRegClass(const TargetRegisterClass &RC, LLT Ty) const
			override;
};

extern HwtFpgaRegisterBankInfo hwtFpgaRegisterBankInfo;

}
