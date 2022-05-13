#include "genericFpgaRegisterBankInfo.h"
#include <llvm/CodeGen/GlobalISel/RegisterBank.h>

namespace llvm {

const size_t genericFpgaRegBanksCnt = 1;
llvm::RegisterBank genericFpgaRegBank0(0/*ID*/,
		"genericFpgaReg" /* only for debugging purposes*/,
		1 << 16/*maximal size in bits that fits in this register bank.*/,
		(const uint32_t*) &genericFpgaRegBanksCnt /*CoveredClasses*/,
		genericFpgaRegBanksCnt);
llvm::RegisterBank *genericFpgaRegBanks[genericFpgaRegBanksCnt] = {
		&genericFpgaRegBank0, };

GenericFpgaRegisterBankInfo::GenericFpgaRegisterBankInfo() :
		llvm::RegisterBankInfo(genericFpgaRegBanks, genericFpgaRegBanksCnt) {
}

GenericFpgaRegisterBankInfo genericFpgaRegisterBankInfo;
}
