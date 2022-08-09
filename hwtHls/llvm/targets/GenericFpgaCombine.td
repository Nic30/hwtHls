include "llvm/Target/GlobalISel/Combine.td"

def extract_const_propagation: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode GENFPGA_EXTRACT):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstExtract(*${root}); }])
>;

def merge_values_const_propagation: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode GENFPGA_MERGE_VALUES):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstMergeValues(*${root}); }])
>;

// convert the G_CONSTANT instructions to CImm operands on all users
def g_constant_to_imm: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode 
  			G_PHI,
  			G_LOAD,
  			G_STORE,
  			G_ADD,
			G_AND,
			G_BR,
			G_BRCOND,
			G_ICMP,
			// this opcodes should not appear in this stage
			// G_EXTRACT,
			// G_INDEXED_LOAD,
			// G_INDEXED_STORE,
			// G_MERGE_VALUES,
			G_PTR_ADD,
			G_MUL,
			G_OR,
			G_SELECT,
			G_SUB,
			G_XOR ,
			G_SEXT,
			G_ZEXT,
			G_SHL,
  			GENFPGA_EXTRACT,
            GENFPGA_MERGE_VALUES ,
            GENFPGA_NOT,
            GENFPGA_CCOPY,
            GENFPGA_MUX,
            GENFPGA_CLOAD,
            GENFPGA_CSTORE,
            PseudoRET):$root, [{ return Helper.hasG_CONSTANTasUse(*${root}); }]),
  (apply [{ return Helper.rewriteG_CONSTANTasUseAsCImm(*${root}); }])
>;

def const_and_eval: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_AND):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstBinOp(*${root}, [](const APInt & a, const APInt & b) { return a & b; }); }])
>;
def const_or_eval: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_OR):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstBinOp(*${root}, [](const APInt & a, const APInt & b) { return a | b; }); }])
>;
def const_xor_eval: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_XOR):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstBinOp(*${root}, [](const APInt & a, const APInt & b) { return a ^ b; }); }])
>;

def const_sub_eval: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_SUB):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstBinOp(*${root}, [](const APInt & a, const APInt & b) { return a - b; }); }])
>;
def const_add_eval: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_ADD):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstBinOp(*${root}, [](const APInt & a, const APInt & b) { return a + b; }); }])
>;
def const_mul_eval: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_MUL):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstBinOp(*${root}, [](const APInt & a, const APInt & b) { return a * b; }); }])
>;

def const_mux_eval : GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode GENFPGA_MUX):$root,
    [{ return Helper.hashSomeConstConditions(*${root}); }]),
  (apply [{ return Helper.rewriteConstCondMux(*${root}); }])
>;

def const_eval_combines : GICombineGroup<[
	extract_const_propagation, merge_values_const_propagation, g_constant_to_imm, const_and_eval, const_or_eval, const_xor_eval,
	const_sub_eval, const_add_eval, const_mul_eval, const_mux_eval
]>;


// perform all known combinations to simplify the code as much as possible before next step
def GenericFpgaGenPreLegalizeGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreLegalizeGICombinerHelper", [
  	all_combines
  ]> {
  let DisableRuleOption = "GenericFpgaGenPreLegalizeGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreLegalizeGICombinerHelperState";
  let AdditionalArguments = [];
}


def copy_to_genfpga_copy : GICombineRule<
  (defs root:$d),
  (match (COPY $d, $s):$mi),
  (apply [{ 
	  	Helper.replaceOpcodeWith(*${mi}, GenericFpga::GENFPGA_CCOPY); 
	  	Observer.changingInstr(*${mi});
		MachineInstrBuilder builder(*MF, ${mi});
  		auto &C = MF->getFunction().getContext();
		auto *CI = ConstantInt::get(C, APInt(1, 1));
		builder.addCImm(CI);
		Observer.changedInstr(*${mi});
  	}])>;

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
  "GenericFpgaGenPreRegAllocGICombinerHelper", [copy_to_genfpga_copy,
                                                extract_on_merge_values,
                                                const_eval_combines
                                                ]> {
  let DisableRuleOption = "GenericFpgaGenPreRegAllocGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreRegAllocGICombinerHelperState";
  let AdditionalArguments = [];
}

// at this point all optimizations should be done and we only format the instructions form more simple conversion to netlist
// * extract muxes to simplify thread detection
// * extract GENFPGA_NOT
// * extract/merge bit concatenations and slices
def GenericFpgaGenPreToNetlistGICombinerHelper: GICombinerHelper<
  "GenericFpgaGenPreToNetlistGICombinerHelper", [xor_right_allOnes,
  												 extract_on_merge_values,
                                                 const_eval_combines
                                                 ]> {
  let DisableRuleOption = "GenericFpgaGenPreToNetlistGICombinerHelper-disable-rule";
  let StateClass = "GenericFpgaGenPreToNetlistGICombinerHelperState";
  let AdditionalArguments = [];
}

