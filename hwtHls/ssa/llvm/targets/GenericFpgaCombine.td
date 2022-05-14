include "llvm/Target/GlobalISel/Combine.td"


// perform all known combinations to simplify the code as much as possible before next step
def GenericFpgaGenPreLegalizeGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreLegalizeGICombinerHelper", [all_combines]> {
  let DisableRuleOption = "GenericFpgaGenPreLegalizeGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreLegalizeGICombinerHelperState";
  let AdditionalArguments = [];
}


def copy_to_genfpga_copy : GICombineRule<
  (defs root:$d),
  (match (COPY $d, $s):$mi),
  (apply [{ Helper.replaceOpcodeWith(*${mi}, GenericFpga::GENFPGA_CCOPY); }])>;

// rewrite generic opcodes to GENFPGA_* where beneficial
def GenericFpgaGenPreRegAllocGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreRegAllocGICombinerHelper", [copy_to_genfpga_copy]> {
  let DisableRuleOption = "GenericFpgaGenPreRegAllocGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreRegAllocGICombinerHelperState";
  let AdditionalArguments = [];
}

// extract muxes to simplify thread detection
def GenericFpgaGenPreToNetlistGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreToNetlistGICombinerHelper", []> {
  let DisableRuleOption = "GenericFpgaGenPreToNetlistGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreToNetlistGICombinerHelperState";
  let AdditionalArguments = [];
}
