
//===----------------------------------------------------------------------===//
// GenericFpga Specific Node Definitions
//===----------------------------------------------------------------------===//

def genericfpga_concat : SDNode<"GenericFpgaISD::BIT_CONCAT", SDTIntBinOp>;
def genericfpga_slice : SDNode<"GenericFpgaISD::BIT_SLICE", SDTIntBinOp>;

//===----------------------------------------------------------------------===//
// GenericFpga predicates for subtarget features
//===----------------------------------------------------------------------===//


//===----------------------------------------------------------------------===//
//===----------------------------------------------------------------------===//
// GenericFpga Instruction list
//===----------------------------------------------------------------------===//
//===----------------------------------------------------------------------===//
class GenericFpgaInst<
             dag outs,
             dag ins,
             //string opcodestr, string argstr,
             list<dag> pattern //,
             //InstFormat format
             >
    : Instruction {
  let Namespace = "GenericFpga";
  dag OutOperandList = outs;
  dag InOperandList = ins;
  let Pattern = pattern;
}

let OperandType = "OPERAND_IMMEDIATE" in {
	def iAnyImm  : Operand<iAny>;
}
//
//def CONST_VAL : GenericFpgaInst<(outs AnyRegCls:$dst),
//	(ins iAnyImm:$src),
//	[(set iAny:$dst, iAnyImm:$src)]> {
//	let isMoveImm = 1;
//} 

def ADDrr : GenericFpgaInst<
    (outs AnyRegCls:$dst),
	(ins AnyRegCls:$src1, AnyRegCls:$src2),
	//"add $dst, $src1, $src2",
	[(set iAny:$dst, (add iAny:$src1, iAny:$src2))]>;
