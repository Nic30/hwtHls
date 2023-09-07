#include "hwtFpgaTargetSubtarget.h"

#include "hwtFpgaTargetMachine.h"
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

#include "hwtFpgaInstrInfo.h"
#include "GISel/hwtFpgaRegisterBankInfo.h"
#include "GISel/hwtFpgaLegalizerInfo.h"
#include "GISel/hwtFpgaInstructionSelector.h"

#define DEBUG_TYPE "hwtfpga-subtarget"

#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "HwtFpgaGenSubtargetInfo.inc"

namespace llvm {

HwtFpgaTargetSubtarget::HwtFpgaTargetSubtarget(const Triple &TT,
		StringRef CPU, StringRef TuneCPU, StringRef FS, StringRef ABIName,
		const TargetMachine &TM) :
		HwtFpgaTargetGenSubtargetInfo(TT, CPU, TuneCPU, FS) {
	TLI.reset(new HwtFpgaTargetLowering(TM, *this));
	TII.reset(new HwtFpgaInstrInfo());
	CallLoweringInfo.reset(new HwtFpgaCallLowering(*TLI));
	Legalizer.reset(new HwtFpgaLegalizerInfo(*this));
	TargetFrameLoweringInfo.reset(
			new HwtFpgaTargetFrameLowering(
					TargetFrameLowering::StackDirection::StackGrowsDown,
					Align(1), -2));
	RegBankInfo.reset(&llvm::hwtFpgaRegisterBankInfo);
	IS.reset(
			createHwtFpgaInstructionSelector(
					static_cast<const HwtFpgaTargetMachine&>(TM), *this,
					static_cast<HwtFpgaRegisterBankInfo&>(*RegBankInfo)));
}

const llvm::TargetLowering* HwtFpgaTargetSubtarget::getTargetLowering() const {
	return TLI.get();
}

const TargetRegisterInfo* HwtFpgaTargetSubtarget::getRegisterInfo() const {
	return &TRI;
}

const TargetInstrInfo* HwtFpgaTargetSubtarget::getInstrInfo() const {
	return TII.get();
}

const llvm::CallLowering* HwtFpgaTargetSubtarget::getCallLowering() const {
	return CallLoweringInfo.get();
}

llvm::InstructionSelector* HwtFpgaTargetSubtarget::getInstructionSelector() const {
	return IS.get();
}

const llvm::LegalizerInfo* HwtFpgaTargetSubtarget::getLegalizerInfo() const {
	return Legalizer.get();
}

const llvm::TargetFrameLowering* HwtFpgaTargetSubtarget::getFrameLowering() const {
	return TargetFrameLoweringInfo.get();
}

const llvm::RegisterBankInfo* HwtFpgaTargetSubtarget::getRegBankInfo() const {
	return RegBankInfo.get();
}

}
