//===---------------------------------------------------------------------===//
// This is the top level entry point for the GenericFpga target.
// This target is meant as an universal target for FPGAs, it does not contain
// any registers and scheduling must be done externally.
//===---------------------------------------------------------------------===//

//===---------------------------------------------------------------------===//
// Target-independent interfaces which we are implementing
//===---------------------------------------------------------------------===//
include "llvm/Target/Target.td"

//===---------------------------------------------------------------------===//
// Dummy register File Description
//===---------------------------------------------------------------------===//

include "GenericFpgaRegisterInfo.td"

//===---------------------------------------------------------------------===//
// Instruction Descriptions
//===---------------------------------------------------------------------===//

include "GenericFpgaInstrInfo.td"


def GenericFpgaInstrInfo : InstrInfo;
//===---------------------------------------------------------------------===//
// Calling Conventions are defined in C++ only
//===---------------------------------------------------------------------===//


//===---------------------------------------------------------------------===//
// Target Declaration (not AssemblyWriters, AssemblyParsers, AssemblyParserVariants
// because we are using machine SSA and not producing assembly at all)
//===---------------------------------------------------------------------===//

def GenericFpgaTarget : Target {
  let InstructionSet  = GenericFpgaInstrInfo;
}
