#include <hwtHls/llvm/targets/hwtFpgaTargetSubtarget.h>

#include <hwtHls/llvm/targets/hwtFpgaTargetMachine.h>
#include <llvm/CodeGen/TargetInstrInfo.h>
#include <llvm/IR/Attributes.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/GlobalValue.h>
#include <llvm/Support/CommandLine.h>
#include <llvm/Support/Debug.h>
#include <llvm/Support/ErrorHandling.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/Target/TargetOptions.h>

#include <hwtHls/llvm/targets/hwtFpgaInstrInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaRegisterBankInfo.h>
#include <hwtHls/llvm/targets/GISel/hwtFpgaInstructionSelector.h>

#define DEBUG_TYPE "hwtfpga-subtarget"

#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "HwtFpgaGenSubtargetInfo.inc"

namespace llvm {

HwtFpgaTargetSubtarget::HwtFpgaTargetSubtarget(const Triple &TT,
		StringRef CPU, StringRef TuneCPU, StringRef FS, StringRef ABIName,
		const TargetMachine &TM) :
		HwtFpgaTargetGenSubtargetInfo(TT, CPU, TuneCPU, FS), TM(TM) {
}

const llvm::TargetLowering* HwtFpgaTargetSubtarget::getTargetLowering() const {
	if (!TLI)
		TLI.reset(new HwtFpgaTargetLowering(TM, *this));
	return TLI.get();
}

const TargetRegisterInfo* HwtFpgaTargetSubtarget::getRegisterInfo() const {
	return &TRI;
}

const TargetInstrInfo* HwtFpgaTargetSubtarget::getInstrInfo() const {
	if (!TII)
		TII.reset(new HwtFpgaInstrInfo());
	return TII.get();
}

const llvm::CallLowering* HwtFpgaTargetSubtarget::getCallLowering() const {
	if (!CallLoweringInfo)
		CallLoweringInfo.reset(new HwtFpgaCallLowering(*TLI));
	return CallLoweringInfo.get();
}

llvm::InstructionSelector* HwtFpgaTargetSubtarget::getInstructionSelector() const {
	if (!IS)
		IS.reset(
			createHwtFpgaInstructionSelector(
					static_cast<const HwtFpgaTargetMachine&>(TM), *this,
					static_cast<const HwtFpgaRegisterBankInfo&>(*RegBankInfo)));
	return IS.get();
}

const llvm::LegalizerInfo* HwtFpgaTargetSubtarget::getLegalizerInfo() const {
	if (!Legalizer)
		Legalizer.reset(new HwtFpgaLegalizerInfo(*this));
	return Legalizer.get();
}

const llvm::TargetFrameLowering* HwtFpgaTargetSubtarget::getFrameLowering() const {
	if (!TargetFrameLoweringInfo)
		TargetFrameLoweringInfo.reset(
			new HwtFpgaTargetFrameLowering(
					TargetFrameLowering::StackDirection::StackGrowsDown,
					Align(1), -2));
	return TargetFrameLoweringInfo.get();
}

const llvm::RegisterBankInfo* HwtFpgaTargetSubtarget::getRegBankInfo() const {
	if (!RegBankInfo)
		RegBankInfo.reset(&llvm::hwtFpgaRegisterBankInfo);
	return RegBankInfo.get();
}

}
