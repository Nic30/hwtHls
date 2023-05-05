//===---------------------------------------------------------------------===//
// This is the top level entry point for the GenericFpga target.
// This target is meant as an universal target for FPGAs, it does not contain
// any physical registers and scheduling must be done externally.
//
// 
// This backend have seaveral expectations from LLVM IR
// * All function arguments represents IO of some component, each function must have hwtHls.param_addr_width metadata.
// * Each parameter pointer has its own address space, where parameter 0 has address space 1,
//   (address space 0 is llvm default and it is left for local memories)
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
include "GenericFpgaCombine.td"
include "GenericFpgaSchedModel.td"

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


def : ProcessorModel<"model0", GenFpgaSchedModel, []>;
