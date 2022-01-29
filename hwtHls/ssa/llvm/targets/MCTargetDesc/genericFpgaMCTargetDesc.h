#pragma once

#include <llvm/MC/MCStreamer.h>
#include <llvm/Support/DataTypes.h>
#include <string>

namespace llvm {
class MCSubtargetInfo;
class Triple;
class StringRef;

//std::string ParseGenericFpgaTriple(const Triple &TT);

/// Create a FPGA MCSubtargetInfo instance. This is exposed so Asm parser, etc.
/// do not need to go through TargetRegistry.
//MCSubtargetInfo* createGenericFpgaMCSubtargetInfo(const Triple &TT,
//		StringRef CPU, StringRef FS);
}
