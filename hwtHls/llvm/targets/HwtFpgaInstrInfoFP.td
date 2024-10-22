

class HwtFpgaFpUn : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$src, 
        // HFloatTmpConfig options
	    i64imm:$exponentOrIntWidth,
		i64imm:$mantissaOrFracWidth,
		i64imm:$isInQFromat,
		i64imm:$supportSubnormal,
		i64imm:$hasSign,
		i64imm:$hasIsNaN,
		i64imm:$hasIsInf,
		i64imm:$hasIs1,
		i64imm:$hasIs0
	),
    []>;
 
class HwtFpgaFpBin : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$src0, anyregcls:$src1,
        // HFloatTmpConfig options
	    i64imm:$exponentOrIntWidth,
		i64imm:$mantissaOrFracWidth,
		i64imm:$isInQFromat,
		i64imm:$supportSubnormal,
		i64imm:$hasSign,
		i64imm:$hasIsNaN,
		i64imm:$hasIsInf,
		i64imm:$hasIs1,
		i64imm:$hasIs0
	),
    []>;

let hasSideEffects = 0 in {
	def HWTFPGA_FP_FNEG: HwtFpgaFpUn;
	def HWTFPGA_FP_FADD: HwtFpgaFpBin;
	def HWTFPGA_FP_FSUB: HwtFpgaFpBin;
	def HWTFPGA_FP_FMUL: HwtFpgaFpBin;
	def HWTFPGA_FP_FDIV: HwtFpgaFpBin;
}