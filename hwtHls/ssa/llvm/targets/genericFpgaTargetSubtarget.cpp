#include "genericFpgaTargetSubtarget.h"

#include "genericFpgaTargetMachine.h"
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
#include <llvm/CodeGen/TargetInstrInfo.h>

#include "genericFpgaRegisterBankInfo.h"
#include "genericFpgaInstrInfo.h"


#define DEBUG_TYPE "genericfpga-subtarget"

#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "GenericFpgaGenSubtargetInfo.inc"

namespace llvm {

GenericFpgaTargetSubtarget::GenericFpgaTargetSubtarget(const Triple &TT,
		StringRef CPU, StringRef TuneCPU, StringRef FS, StringRef ABIName,
		const TargetMachine &TM) :
		GenericFpgaTargetGenSubtargetInfo(TT, CPU, TuneCPU, FS) {
	TLI.reset(new llvm::GenericFpgaTargetLowering(TM, *this));
	// TTI(TM.createDataLayout())
	CallLoweringInfo.reset(new llvm::GenericFpgaCallLowering(*TLI));
	//InstSelector.reset(nullptr);
	Legalizer.reset(nullptr);
	TargetFrameLoweringInfo.reset(
			new llvm::GenericFpgaTargetFrameLowering(
					TargetFrameLowering::StackDirection::StackGrowsDown,
					Align(1), -2));
	SelectionDAGTargetInfoInfo.reset(new SelectionDAGTargetInfo());
	RegBankInfo.reset(&llvm::genericFpgaRegisterBankInfo);
}

const llvm::TargetLowering* GenericFpgaTargetSubtarget::getTargetLowering() const {
	return TLI.get();
}
const TargetRegisterInfo* GenericFpgaTargetSubtarget::getRegisterInfo() const {
	return &TRI;
}
const llvm::SelectionDAGTargetInfo* GenericFpgaTargetSubtarget::getSelectionDAGInfo() const {
	return SelectionDAGTargetInfoInfo.get();
}

llvm::GenericFpgaInstrInfo GenericFpgaSubtargetTII;
const TargetInstrInfo* GenericFpgaTargetSubtarget::getInstrInfo() const {
	return &GenericFpgaSubtargetTII;
}
std::vector<SubtargetSubTypeKV> GenericFpgaTargetSubtarget::_PD;
std::vector<MCWriteProcResEntry> GenericFpgaTargetSubtarget::_WPR;
std::vector<MCWriteLatencyEntry> GenericFpgaTargetSubtarget::_WL;
std::vector<MCReadAdvanceEntry> GenericFpgaTargetSubtarget::_RA;

}
