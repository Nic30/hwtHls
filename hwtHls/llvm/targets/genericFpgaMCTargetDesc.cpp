#include "genericFpgaMCTargetDesc.h"

#include <llvm/ADT/StringRef.h>
#include <llvm/ADT/Twine.h>
#include <llvm/MC/MCSubtargetInfo.h>
#include <llvm/MC/MCInstrInfo.h>
#include <llvm/MC/MCRegisterInfo.h>
#include <llvm/MC/MCSubtargetInfo.h>
#include <llvm/MC/TargetRegistry.h>
#include <llvm/Support/Compiler.h>
#include "genericFpgaTargetInfo.h"

#define GET_INSTRINFO_MC_DESC
#include "GenericFpgaGenInstrInfo.inc"

#define GET_SUBTARGETINFO_MC_DESC
#include "GenericFpgaGenSubtargetInfo.inc"

#define GET_REGINFO_MC_DESC
#include "GenericFpgaGenRegisterInfo.inc"

using namespace llvm;

//std::string ParseGenericFpgaTriple(const Triple &TT) {
//	std::string FS;
//	return FS;
//}

//MCSubtargetInfo* createGenericFpgaMCSubtargetInfo(const Triple &TT,
//		StringRef CPU, StringRef FS) {
//	std::string ArchFS = ParseGenericFpgaTriple(TT);
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
//	return createGenericFpgaMCSubtargetInfo(TT, CPUName, ArchFS);
//}

MCInstrInfo* createGenericFpgaMCInstrInfo() {
	MCInstrInfo *X = new MCInstrInfo();
	llvm::InitGenericFpgaTargetMCInstrInfo(X);
	return X;
}
static MCRegisterInfo* createGenericFpgaMCRegisterInfo(const Triple &TT) {
	MCRegisterInfo *X = new MCRegisterInfo();
	llvm::InitGenericFpgaTargetMCRegisterInfo(X,
			0 /* return address register*/);
	return X;
}

static MCSubtargetInfo* createGenericFpgaMCSubtargetInfo(const Triple &TT,
		StringRef CPU, StringRef FS) {
	return createGenericFpgaTargetMCSubtargetInfoImpl(TT, CPU, /*TuneCPU*/CPU,
			FS);
}

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeGenericFpgaTargetMC() {
	// Register the MC instruction info.

	TargetRegistry::RegisterMCInstrInfo(getTheGenericFpgaTarget(),
			createGenericFpgaMCInstrInfo);

	// Register the MC register info.
	TargetRegistry::RegisterMCRegInfo(getTheGenericFpgaTarget(),
			createGenericFpgaMCRegisterInfo);

	// Register the MC subtarget info.
	TargetRegistry::RegisterMCSubtargetInfo(getTheGenericFpgaTarget(),
			createGenericFpgaMCSubtargetInfo);
}
