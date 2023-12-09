include "llvm/Target/GlobalISel/Combine.td"


/*************************************************************************************/
// Definitions of combiner rules
/*************************************************************************************/

def extract_const_propagation: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode HWTFPGA_EXTRACT):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstExtract(*${root}); }])
>;

def merge_values_const_propagation: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode HWTFPGA_MERGE_VALUES):$root,
    [{ return Helper.hashOnlyConstUses(*${root}); }]),
  (apply [{ return Helper.rewriteConstMergeValues(*${root}); }])
>;

def trivial_copy_propagate_matchdata : GIDefMatchData<"bool">;
def trivial_copy_propagate: GICombineRule<
  (defs root:$root, trivial_copy_propagate_matchdata:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.isTrivialRemovableCopy(*${root}, ${matchinfo}); }]),
  (apply [{ return Helper.rewriteTrivialRemovableCopy(*${root}, ${matchinfo}); }])
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
			G_UDIV,
			G_SDIV,
			G_UREM,
			G_SREM,
			G_OR,
			G_SELECT,
			G_SUB,
			G_XOR ,
			G_SEXT,
			G_ZEXT,
			G_SHL,
			G_LSHR,
			G_ASHR,
  			HWTFPGA_EXTRACT,
            HWTFPGA_MERGE_VALUES,
            HWTFPGA_NOT,
            HWTFPGA_MUX,
            HWTFPGA_CLOAD,
            HWTFPGA_CSTORE,
            PseudoRET):$root, [{ return Helper.hasG_CONSTANTasUse(*${root}); }]),
  (apply [{ return Helper.rewriteG_CONSTANTasUseAsCImm(*${root}); }])
>;

// merge 2 instruction with successor if they have same use operands and
// the def operands have both only a single user
def trivial_instr_deduplication: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode 
			G_PTR_ADD,
			G_MUL,
			G_UDIV,
			G_SDIV,
			G_UREM,
			G_SREM,
			G_OR,
			G_SELECT,
			G_SUB,
			G_XOR ,
			G_SEXT,
			G_ZEXT,
			G_SHL,
			G_LSHR,
			G_ASHR,
			HWTFPGA_EXTRACT,
            HWTFPGA_MERGE_VALUES,
            HWTFPGA_NOT,
            HWTFPGA_MUX,
            HWTFPGA_ADD,
			HWTFPGA_AND,
			HWTFPGA_ICMP,
			HWTFPGA_MUL,
			HWTFPGA_UDIV,
			HWTFPGA_SDIV,
			HWTFPGA_UREM,
			HWTFPGA_SREM,
			HWTFPGA_OR,
			HWTFPGA_SUB,
			HWTFPGA_XOR
		):$root,
    [{ return Helper.matchTrivialInstrDuplication(*${root}); }]),
  (apply [{ return Helper.rewriteTrivialInstrDuplication(*${root}); }])
>;

def undef_propagation: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode HWTFPGA_EXTRACT, HWTFPGA_NOT):$root,
         [{ return Helper.matchAnyExplicitUseIsUndef(*${root}); }]),
  (apply [{ Helper.replaceInstWithUndef(*${root}); }])>;

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

// strip mux cases which can be evaluated immedietly
def const_mux_eval : GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.hashSomeConstConditions(*${root}); }]),
  (apply [{ return Helper.rewriteConstCondMux(*${root}); }])
>;

// convert cond ? 1:0 -> cond,
//         cond ? 0:1 -> HWTFPGA_NOT cond,
//         cond ? x:x -> x
def const_val_mux_eval_matchdata : GIDefMatchData<"hwtHls::CImmOrRegWithNegFlag">;
def const_val_mux_eval : GICombineRule<
  (defs root:$root, const_val_mux_eval_matchdata:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.hasAll1AndAll0Values(*${root}, ${matchinfo}); }]),
  (apply [{ return Helper.rewriteConstValMux(*${root}, ${matchinfo}); }])
>;

// // generalized const_val_mux_eval which probes every bit for every condition operand separately
// def mux_sink_directly_cond_driven_val_bits_matchdata : GIDefMatchData<"hwtHls::MuxDirectlyCondDrivenBits">;
// def mux_sink_directly_cond_driven_val_bits : GICombineRule<
//   (defs root:$root, mux_sink_directly_cond_driven_val_bits_matchdata:$matchinfo),
//   (match (wip_match_opcode HWTFPGA_MUX):$root,
//     [{ return Helper.matchMuxSinkDirectlyCondDrivenValBits(*${root}, ${matchinfo}); }]),
//   (apply [{ return Helper.rewriteMuxSinkDirectlyCondDrivenValBits(*${root}, ${matchinfo}); }])
// >;

// if mux values are HWTFPGA_MERGE_VALUES check if there are same bits in every value, if this is the case
// replace this instruction with a new mux of values without same bits and a HWTFPGA_MERGE_VALUES
// (possibly also HWTFPGA_EXTRACT on new HWTFPGA_MUX) of reduced value with removed value
// to form a result which replaces original HWTFPGA_MUX instruction
// There are multiple different cases for same bits
// * bits are same constant or undef in every value
// * bits are same reg or undef in every value
// * bits are undef in every value
// One operand of value operand defined by constant or HWTFPGA_MERGE_VALUES or HWTFPGA_MUX with a single operand or IMPLICIT_DEF
// may be split to multiple parts to extract same parts
def mux_trivial_const_propagation_matchdata : GIDefMatchData<"hwtHls::MuxReducibleValuesInfo">;
def mux_trivial_const_propagation: GICombineRule<
  (defs root:$root, mux_trivial_const_propagation_matchdata:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.matchMuxForConstPropagation(*${root}, ${matchinfo}); }]),
  (apply [{ return Helper.rewriteMuxConstPropagation(*${root}, ${matchinfo}); }])
>;

// remove cases from end which have same T and F value
def mux_redundant_case_reduce_matchdata : GIDefMatchData<"SmallVector<unsigned>">; // indexes of duplicit condition operands
def mux_redundant_case_reduce: GICombineRule<
  (defs root:$root, mux_redundant_case_reduce_matchdata:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.matchMuxRedundantCase(*${root}, ${matchinfo}); }]),
  (apply [{ return Helper.rewriteMuxRmCases(*${root}, ${matchinfo}); }])
>;

def const_merge_values_matchdata : GIDefMatchData<"llvm::APInt">;
def const_merge_values_eval: GICombineRule<
  (defs root:$root, const_merge_values_matchdata:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MERGE_VALUES):$root,
         [{ return Helper.matchConstMergeValues(*${root}, ${matchinfo}); }]),
  (apply [{ Helper.rewriteConstMergeValues(*${root}, ${matchinfo}); }])>;
 

def const_eval_combines : GICombineGroup<[
	extract_const_propagation,
	merge_values_const_propagation,
	g_constant_to_imm,
	const_and_eval,
	const_or_eval,
	const_xor_eval,
	const_sub_eval,
	const_add_eval,
	const_mul_eval,
	const_mux_eval,
	const_val_mux_eval,
	undef_propagation,
	const_merge_values_eval,
	mux_redundant_case_reduce,
]>;


// perform all known combinations to simplify the code as much as possible before next step
def HwtFpgaGenPreLegalizeGICombinerHelper: GICombinerHelper<
  "HwtFpgaGenPreLegalizeGICombinerHelper", [
  	all_combines
  ]> {
  let DisableRuleOption = "HwtFpgaGenPreLegalizeGICombinerHelper-disable-rule";
  let StateClass = "HwtFpgaGenPreLegalizeGICombinerHelperState";
  let AdditionalArguments = [];
}


def copy_to_HWTFPGA_mux : GICombineRule<
  (defs root:$d),
  (match (COPY $d, $s):$mi),
  (apply [{
	  	Helper.replaceOpcodeWith(*${mi}, HwtFpga::HWTFPGA_MUX);
  	}])>;

// Fold (x G_XOR allOnes) - > HWTFPGA_NOT x
def xor_right_allOnes: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_XOR):$root,
    [{ return Helper.matchOperandIsAllOnes(*${root}, 2); }]),
  (apply [{ return Helper.rewriteXorToNot(*${root}); }])
>;

// Fold (HWTFPGA_EXTRACT (HWTFPGA_MERGE_VALUES ...)) -> HWTFPGA_MERGE_VALUES of just selected parts
def extract_on_merge_values: GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode HWTFPGA_EXTRACT):$root,
    [{ return Helper.matchIsExtractOnMergeValues(*${root}); }]),
  (apply [{ return Helper.rewriteExtractOnMergeValues(*${root}); }])
>;


//
// Fold (HWTFPGA_MUX (... HWTFPGA_MUX ...)) -> HWTFPGA_MUX ...
def mux_merge_matchdata : GIDefMatchData<"llvm::SmallVector<bool>">;
def mux_merge: GICombineRule<
  (defs root:$root, mux_merge_matchdata:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.matchNestedMux(*${root}, ${matchinfo}); }]),
  (apply [{ return Helper.rewriteNestedMuxToMux(*${root}, ${matchinfo}); }])
>;

// (MUX  x, c, 0) -> (G_AND|HWTFPGA_AND x, (SEXT c))
// (MUX -1, c, x) -> (G_OR|HWTFPGA_OR x, (SEXT c))
//  (SEXT is avoided if x.width == 1)
def mux_mask_to_and_or_mask: GICombineRule<
  (defs root:$root, build_fn_matchinfo:$matchinfo),
  (match (wip_match_opcode HWTFPGA_MUX):$root,
    [{ return Helper.matchMuxMask(*${root}, ${matchinfo}); }]),
  (apply [{ Helper.applyBuildFn(*${root}, ${matchinfo}); }])
>;

// (SGE x,  0) -> NOT x.msb
// (SGT x, -1) -> NOT x.msb
// (SLT x,  0) -> x.msb
// (SGT x, -1) -> x.msb
def extract_msb_cmp: GICombineRule<
  (defs root:$root, build_fn_matchinfo:$info),
  (match (wip_match_opcode G_ICMP):$root,
    [{ return Helper.matchCmpToMsbCheck(*${root}, ${info}); }]),
  (apply [{ Helper.applyBuildFn(*${root}, ${info}); }])
>;

def constCmpConstAdd_to_constCmp: GICombineRule<
  (defs root:$root, build_fn_matchinfo:$info),
  (match (wip_match_opcode G_ICMP, HWTFPGA_ICMP):$root,
    [{ return Helper.matchConstCmpConstAdd(*${root}, ${info}); }]),
  (apply [{ Helper.applyBuildFn(*${root}, ${info}); }])
>;

/*************************************************************************************/
// Definitions of combiner helper classes
/*************************************************************************************/


// rewrite generic opcodes to HWTFPGA_* where beneficial
def HwtFpgaGenPreRegAllocGICombinerHelper: GICombinerHelper<
  "HwtFpgaGenPreRegAllocGICombinerHelper", [
  	copy_to_HWTFPGA_mux,
    extract_on_merge_values,
    const_eval_combines,
    trivial_copy_propagate,
    mux_trivial_const_propagation,
    ]> {
  let DisableRuleOption = "HwtFpgaGenPreRegAllocGICombinerHelper-disable-rule";
  let StateClass = "HwtFpgaGenPreRegAllocGICombinerHelperState";
  let AdditionalArguments = [];
}
// rewrite all remaining generic opcodes to HWTFPGA_*
def generic_opcode_to_hwtfpga : GICombineRule<
  (defs root:$root),
  (match (wip_match_opcode G_ADD, G_AND, G_BR, G_BRCOND, G_ICMP, G_MUL, G_SDIV, G_UDIV, G_UREM, G_SREM, G_OR, G_SUB, G_XOR, G_GLOBAL_VALUE, G_IMPLICIT_DEF):$root),
  (apply [{ Helper.genericOpcodeToHwtfpga(*${root}); }])
 >;

// at this point all optimizations should be done and we only format the instructions form more simple conversion to netlist
// * extract muxes to simplify thread detection
// * extract HWTFPGA_NOT
// * extract/merge bit concatenations and slices
def HwtFpgaGenPreToNetlistGICombinerHelper: GICombinerHelper<
  "HwtFpgaGenPreToNetlistGICombinerHelper", [
    mux_mask_to_and_or_mask,
  	xor_right_allOnes,
  	extract_on_merge_values,
    const_eval_combines,
    mux_merge,
    mux_trivial_const_propagation,
    extract_msb_cmp,
    constCmpConstAdd_to_constCmp,
    trivial_copy_propagate,
    generic_opcode_to_hwtfpga,
    ]> {
  let DisableRuleOption = "HwtFpgaGenPreToNetlistGICombinerHelper-disable-rule";
  let StateClass = "HwtFpgaGenPreToNetlistGICombinerHelperState";
  let AdditionalArguments = [];
}

