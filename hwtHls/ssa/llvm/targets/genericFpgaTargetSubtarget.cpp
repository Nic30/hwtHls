#include "genericFpgaTargetSubtarget.h"

#include "genericFpgaTargetMachine.h"
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/GlobalValue.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Support/Host.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/Target/TargetOptions.h>

#include "genericFpgaInstrInfo.h"
#include "GISel/genericFpgaRegisterBankInfo.h"
#include "GISel/genericFpgaLegalizerInfo.h"
#include "GISel/genericFpgaInstructionSelector.h"

#define DEBUG_TYPE "genericfpga-subtarget"

#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "GenericFpgaGenSubtargetInfo.inc"

namespace llvm {

GenericFpgaTargetSubtarget::GenericFpgaTargetSubtarget(const Triple &TT,
		StringRef CPU, StringRef TuneCPU, StringRef FS, StringRef ABIName,
		const TargetMachine &TM) :
		GenericFpgaTargetGenSubtargetInfo(TT, CPU, TuneCPU, FS) {
	TLI.reset(new GenericFpgaTargetLowering(TM, *this));
	TII.reset(new GenericFpgaInstrInfo());
	CallLoweringInfo.reset(new GenericFpgaCallLowering(*TLI));
	Legalizer.reset(new GenericFpgaLegalizerInfo(*this));
	TargetFrameLoweringInfo.reset(
			new GenericFpgaTargetFrameLowering(
					TargetFrameLowering::StackDirection::StackGrowsDown,
					Align(1), -2));
	RegBankInfo.reset(&llvm::genericFpgaRegisterBankInfo);
	IS.reset(
			createGenericFpgaInstructionSelector(
					static_cast<const GenericFpgaTargetMachine&>(TM), *this,
					static_cast<GenericFpgaRegisterBankInfo&>(*RegBankInfo)));
}

const llvm::TargetLowering* GenericFpgaTargetSubtarget::getTargetLowering() const {
	return TLI.get();
}

const TargetRegisterInfo* GenericFpgaTargetSubtarget::getRegisterInfo() const {
	return &TRI;
}

const TargetInstrInfo* GenericFpgaTargetSubtarget::getInstrInfo() const {
	return TII.get();
}

const llvm::CallLowering* GenericFpgaTargetSubtarget::getCallLowering() const {
	return CallLoweringInfo.get();
}

llvm::InstructionSelector* GenericFpgaTargetSubtarget::getInstructionSelector() const {
	return IS.get();
}

const llvm::LegalizerInfo* GenericFpgaTargetSubtarget::getLegalizerInfo() const {
	return Legalizer.get();
}

const llvm::TargetFrameLowering* GenericFpgaTargetSubtarget::getFrameLowering() const {
	return TargetFrameLoweringInfo.get();
}

const llvm::RegisterBankInfo* GenericFpgaTargetSubtarget::getRegBankInfo() const {
	return RegBankInfo.get();
}

}
