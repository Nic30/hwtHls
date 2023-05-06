#pragma once

#include <llvm/MC/MCStreamer.h>
#include <llvm/Support/DataTypes.h>
#include <llvm/Support/DataTypes.h>
#include <llvm/CodeGen/TargetSubtargetInfo.h>

#include <string>

namespace llvm {
class MCSubtargetInfo;
class Triple;
class StringRef;

//std::string ParseHwtFpgaTriple(const Triple &TT);

/// Create a FPGA MCSubtargetInfo instance. This is exposed so Asm parser, etc.
/// do not need to go through TargetRegistry.
//MCSubtargetInfo* createHwtFpgaMCSubtargetInfo(const Triple &TT,
//		StringRef CPU, StringRef FS);

}

#define GET_REGINFO_ENUM
#include "HwtFpgaGenRegisterInfo.inc"

#define GET_INSTRINFO_ENUM
#include "HwtFpgaGenInstrInfo.inc"

#define GET_SUBTARGETINFO_ENUM
#include "HwtFpgaGenSubtargetInfo.inc"

llvm::MCInstrInfo* createHwtFpgaMCInstrInfo();

