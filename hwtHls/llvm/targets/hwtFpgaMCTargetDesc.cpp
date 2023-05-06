#include "hwtFpgaMCTargetDesc.h"

#include <llvm/ADT/StringRef.h>
#include <llvm/ADT/Twine.h>
#include <llvm/MC/MCSubtargetInfo.h>
#include <llvm/MC/MCInstrInfo.h>
#include <llvm/MC/MCRegisterInfo.h>
#include <llvm/MC/MCSubtargetInfo.h>
#include <llvm/MC/TargetRegistry.h>
#include <llvm/Support/Compiler.h>
#include "hwtFpgaTargetInfo.h"

#define GET_INSTRINFO_MC_DESC
#include "HwtFpgaGenInstrInfo.inc"

#define GET_SUBTARGETINFO_MC_DESC
#include "HwtFpgaGenSubtargetInfo.inc"

#define GET_REGINFO_MC_DESC
#include "HwtFpgaGenRegisterInfo.inc"

using namespace llvm;

//std::string ParseHwtFpgaTriple(const Triple &TT) {
//	std::string FS;
//	return FS;
//}

//MCSubtargetInfo* createHwtFpgaMCSubtargetInfo(const Triple &TT,
//		StringRef CPU, StringRef FS) {
//	std::string ArchFS = ParseHwtFpgaTriple(TT);
//	if (!FS.empty()) {
//		if (!ArchFS.empty())
//			ArchFS = (Twine(ArchFS) + "," + FS).str();
//		else
//			ArchFS = FS.str();
//	}
//
//	std::string CPUName = CPU.str();
//	if (CPUName.empty())
//		CPUName = "generic";
//
//	return createHwtFpgaMCSubtargetInfo(TT, CPUName, ArchFS);
//}

MCInstrInfo* createHwtFpgaMCInstrInfo() {
	MCInstrInfo *X = new MCInstrInfo();
	llvm::InitHwtFpgaTargetMCInstrInfo(X);
	return X;
}
static MCRegisterInfo* createHwtFpgaMCRegisterInfo(const Triple &TT) {
	MCRegisterInfo *X = new MCRegisterInfo();
	llvm::InitHwtFpgaTargetMCRegisterInfo(X,
			0 /* return address register*/);
	return X;
}

static MCSubtargetInfo* createHwtFpgaMCSubtargetInfo(const Triple &TT,
		StringRef CPU, StringRef FS) {
	return createHwtFpgaTargetMCSubtargetInfoImpl(TT, CPU, /*TuneCPU*/CPU,
			FS);
}

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeHwtFpgaTargetMC() {
	// Register the MC instruction info.

	TargetRegistry::RegisterMCInstrInfo(getTheHwtFpgaTarget(),
			createHwtFpgaMCInstrInfo);

	// Register the MC register info.
	TargetRegistry::RegisterMCRegInfo(getTheHwtFpgaTarget(),
			createHwtFpgaMCRegisterInfo);

	// Register the MC subtarget info.
	TargetRegistry::RegisterMCSubtargetInfo(getTheHwtFpgaTarget(),
			createHwtFpgaMCSubtargetInfo);
}
