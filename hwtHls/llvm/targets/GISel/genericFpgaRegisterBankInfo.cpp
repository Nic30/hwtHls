#include "genericFpgaRegisterBankInfo.h"
#include <llvm/CodeGen/MachineInstr.h>
#include <iostream>

namespace llvm {

const size_t genericFpgaRegBanksCnt = 1;
llvm::RegisterBank genericFpgaRegBank0(0/*ID*/,
		"genericFpgaReg" /* only for debugging purposes*/,
		1 << 16/*maximal size in bits that fits in this register bank.*/,
		(const uint32_t*) &genericFpgaRegBanksCnt /*CoveredClasses*/,
		genericFpgaRegBanksCnt);
llvm::RegisterBank *genericFpgaRegBanks[genericFpgaRegBanksCnt] = {
		&genericFpgaRegBank0, };

uint32_t AnyRegBankMask = 1;
GenericFpgaRegisterBankInfo::GenericFpgaRegisterBankInfo() :
		llvm::RegisterBankInfo(genericFpgaRegBanks, genericFpgaRegBanksCnt), AnyRegBank(
		/* ID */0, /* Name */"AnyReg", /* Size in bits */1 << 16, /* CoveredRegClasses */
		&AnyRegBankMask, /* NumRegClasses */1)
//, ControlRegBank(/* ID */0, /* Name */
//		"ControlReg", /* Size in bits */1 << 16, /* CoveredRegClasses */
//		nullptr, /* NumRegClasses */0)
{
}

// :note: used in RegBankSelect (regbankselect) pass
// :note: based on MipsRegisterBankInfo::getInstrMapping
const RegisterBankInfo::InstructionMapping& GenericFpgaRegisterBankInfo::getInstrMapping(
		const MachineInstr &MI) const {

	unsigned Opc = MI.getOpcode();

	// Try the default logic for non-generic instructions that are either copies
	// or already have some operands assigned to banks.
	if (!isPreISelGenericOpcode(Opc) || Opc == TargetOpcode::G_PHI) {
		const InstructionMapping &Mapping = getInstrMappingImpl(MI);
		if (Mapping.isValid())
			return Mapping;
	}
	const RegisterBankInfo::InstructionMapping &Mapping = getInstrMappingImpl(
			MI);
	if (Mapping.isValid())
		return Mapping;

	unsigned NumOperands = MI.getNumOperands();
	// [fixme]: double memory leak
	const RegisterBankInfo::PartialMapping *PM =
			new RegisterBankInfo::PartialMapping(0, 1 << 16, AnyRegBank);
	const ValueMapping *VM = new RegisterBankInfo::ValueMapping(PM, 1);
	const ValueMapping *CVM = nullptr;

	using namespace TargetOpcode;
	const ValueMapping *OperandsMapping;
	unsigned MappingID = DefaultMappingID;
	switch (Opc) {
	case G_FRAME_INDEX:
	case G_GLOBAL_VALUE:
	case G_JUMP_TABLE:
	case G_BRCOND:
		assert(NumOperands == 2);
		OperandsMapping = getOperandsMapping( { VM, CVM });
		break;
	case G_BRJT:
		assert(NumOperands == 3);
		OperandsMapping = getOperandsMapping( { VM, CVM, VM });
		break;
	case G_ICMP:
		assert(NumOperands == 4);
		OperandsMapping = getOperandsMapping( { VM, CVM, VM, VM });
		break;
	default:
		SmallVector<const RegisterBankInfo::ValueMapping*> _OperandsMapping;
		for (unsigned i = 0; i < NumOperands; i++) {
			_OperandsMapping.push_back(VM);
		}
		OperandsMapping = getOperandsMapping(_OperandsMapping);
	}

	return getInstructionMapping(MappingID, /*Cost=*/1, OperandsMapping,
			NumOperands);
}
const RegisterBank&
GenericFpgaRegisterBankInfo::getRegBankFromRegClass(
		const TargetRegisterClass &RC, LLT Ty) const {
	return AnyRegBank;
}
GenericFpgaRegisterBankInfo genericFpgaRegisterBankInfo;
}