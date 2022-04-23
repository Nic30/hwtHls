#pragma once
#include <llvm/CodeGen/GlobalISel/RegisterBankInfo.h>

namespace llvm {

class GenericFpgaRegisterBankInfo: public llvm::RegisterBankInfo {
public:
	GenericFpgaRegisterBankInfo();
};

extern GenericFpgaRegisterBankInfo genericFpgaRegisterBankInfo;

}
