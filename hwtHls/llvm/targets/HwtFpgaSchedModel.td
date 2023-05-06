
// represents struct MCSchedModel (which also specifies default values)
def HwtFpgaSchedModel : SchedMachineModel {
  // MispredictPenalty and IssueWidth are not ciritical because instructions in FPGA will be executed in parallel
  // but the value must be high enough to enable ifconversion and earlyifconversion
  let IssueWidth = 65536;
  let MicroOpBufferSize = 65536;
  let LoopMicroOpBufferSize = 65536;
  let LoadLatency = 1;
  let MispredictPenalty = 4096;

  // Allow scheduler to assign default model to any unrecognized opcodes.
  let CompleteModel = 0;
}

// :note: no functional units, no buffers because we do not have this information yet 
let SchedModel = HwtFpgaSchedModel in {
}