#include "genericFpgaSubtarget.h"
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

using namespace llvm;

GenericFpgaSubtarget::GenericFpgaSubtarget(const Triple &TT, StringRef CPU,
		StringRef TuneCPU, StringRef FS, StringRef ABIName,
		const TargetMachine &TM) :
		TargetSubtargetInfo(TT, CPU, TuneCPU, FS, makeArrayRef(_PF),
				makeArrayRef(_PD), &_WPR[0], &_WL[0], &_RA[0], nullptr, nullptr,
				nullptr) {
	CallLoweringInfo.reset(nullptr);
	InstSelector.reset(nullptr);
	Legalizer.reset(nullptr);
	RegBankInfo.reset(nullptr);
}

std::vector<SubtargetSubTypeKV> GenericFpgaSubtarget::_PD;
std::vector<MCWriteProcResEntry> GenericFpgaSubtarget::_WPR;
std::vector<MCWriteLatencyEntry> GenericFpgaSubtarget::_WL;
std::vector<MCReadAdvanceEntry> GenericFpgaSubtarget::_RA;

