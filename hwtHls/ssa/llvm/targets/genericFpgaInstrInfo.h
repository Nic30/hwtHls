#pragma once
#include <llvm/CodeGen/TargetInstrInfo.h>

#include "genericFpgaRegisterInfo.h"

#define GET_INSTRINFO_HEADER
#include "GenericFpgaGenInstrInfo.inc"
#undef GET_INSTRINFO_HEADER

namespace llvm {

class GenericFpgaInstrInfo: public llvm::GenericFpgaTargetGenInstrInfo {
public:
	explicit GenericFpgaInstrInfo();
	const GenericFpgaRegisterInfo& getRegisterInfo() const {
		return RI;
	}

private:
	const GenericFpgaRegisterInfo RI;
};

}
