#include "genericFpgaMCTargetDesc.h"

#include <llvm/ADT/StringRef.h>
#include <llvm/ADT/Twine.h>
#include <llvm/MC/MCSubtargetInfo.h>
#include <llvm/Support/Compiler.h>

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

extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializeGenericFpgaTargetMC() {
	// No MC info, analysis, parser or printer to register.
}
