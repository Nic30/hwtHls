#include "genericFpgaInstrInfo.h"

#define GET_INSTRINFO_CTOR_DTOR
#include "GenericFpgaGenInstrInfo.inc"

namespace llvm {

GenericFpgaInstrInfo::GenericFpgaInstrInfo() :
		GenericFpgaTargetGenInstrInfo(-1, -1, -1, -1), RI() {
}

}
