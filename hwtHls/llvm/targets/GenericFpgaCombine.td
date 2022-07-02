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

// Fold (x G_XOR allOnes) - > GENFPGA_NOT x 
def xor_right_allOnes: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_XOR):$root,
    [{ return Helper.matchOperandIsAllOnes(*${root}, 2); }]),
  (apply [{ return Helper.rewriteXorToNot(*${root}); }])
>;

// Fold (GENFPGA_EXTRACT (GENFPGA_MERGE_VALUES ...)) -> GENFPGA_MERGE_VALUES of just selected parts
def extract_on_merge_values: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode GENFPGA_EXTRACT):$root,
    [{ return Helper.matchIsExtractOnMergeValues(*${root}); }]),
  (apply [{ return Helper.rewriteExtractOnMergeValues(*${root}); }])
>;

// rewrite generic opcodes to GENFPGA_* where beneficial
def GenericFpgaGenPreRegAllocGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreRegAllocGICombinerHelper", [copy_to_genfpga_copy, extract_on_merge_values]> {
  let DisableRuleOption = "GenericFpgaGenPreRegAllocGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreRegAllocGICombinerHelperState";
  let AdditionalArguments = [];
}

// at this point all optimizations should be done and we only format the instructions form more simple conversion to netlist
// * extract muxes to simplify thread detection
// * extract GENFPGA_NOT
// * extract/merge bit concatenations and slices
def GenericFpgaGenPreToNetlistGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreToNetlistGICombinerHelper", [xor_right_allOnes, extract_on_merge_values]> {
  let DisableRuleOption = "GenericFpgaGenPreToNetlistGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreToNetlistGICombinerHelperState";
  let AdditionalArguments = [];
}

