

class HwtFpgaFpUn : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$src, 
        // HFloatTmpConfig options
		i64imm:$isInQFormat,
	    i64imm:$exponentOrIntWidth,
		i64imm:$mantissaOrFracWidth,
		i64imm:$supportSubnormal,
		i64imm:$hasSign,
		i64imm:$hasIsNaN,
		i64imm:$hasIsInf,
		i64imm:$hasIs1,
		i64imm:$hasIs0,
		i64imm:$rounding,
		i64imm:$saturation
	),
    []>;

class HwtFpgaFpUnBinRes : HwtFpgaInst<
    (outs anyregcls:$dst0, anyregcls:$dst1),
    (ins anyregcls:$src, 
        // HFloatTmpConfig options
		i64imm:$isInQFormat,
	    i64imm:$exponentOrIntWidth,
		i64imm:$mantissaOrFracWidth,
		i64imm:$supportSubnormal,
		i64imm:$hasSign,
		i64imm:$hasIsNaN,
		i64imm:$hasIsInf,
		i64imm:$hasIs1,
		i64imm:$hasIs0,
		i64imm:$rounding,
		i64imm:$saturation
	),
    []>;
 
class HwtFpgaFpBin : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$src0, anyregcls:$src1,
        // HFloatTmpConfig options
		i64imm:$isInQFormat,
	    i64imm:$exponentOrIntWidth,
		i64imm:$mantissaOrFracWidth,
		i64imm:$supportSubnormal,
		i64imm:$hasSign,
		i64imm:$hasIsNaN,
		i64imm:$hasIsInf,
		i64imm:$hasIs1,
		i64imm:$hasIs0,
		i64imm:$rounding,
		i64imm:$saturation
	),
    []>;
class HwtFpgaFpBinBinRes: HwtFpgaInst<
    (outs anyregcls:$dst0, anyregcls:$dst1),
    (ins anyregcls:$src0, anyregcls:$src1,
        // HFloatTmpConfig options
		i64imm:$isInQFormat,
	    i64imm:$exponentOrIntWidth,
		i64imm:$mantissaOrFracWidth,
		i64imm:$supportSubnormal,
		i64imm:$hasSign,
		i64imm:$hasIsNaN,
		i64imm:$hasIsInf,
		i64imm:$hasIs1,
		i64imm:$hasIs0,
		i64imm:$rounding,
		i64imm:$saturation
	),
    []>;
    
let hasSideEffects = 0 in {
    def HWTFPGA_FP_FNEG: HwtFpgaFpUn; // -x
	def HWTFPGA_FP_FADD: HwtFpgaFpBin;
	def HWTFPGA_FP_FSUB: HwtFpgaFpBin;
	def HWTFPGA_FP_FMUL: HwtFpgaFpBin; // multiplication where result has same width as operands (there is no difference between signed/unsigned)
	def HWTFPGA_FP_FMUL_S_HL: HwtFpgaFpBin; // signed multiplication where result has 2x width (of mantisa or int and frac part)
	def HWTFPGA_FP_FMUL_U_HL: HwtFpgaFpBin; // unsgigned variant of HWTFPGA_FP_FMUL_S_HL
	def HWTFPGA_FP_FDIV: HwtFpgaFpBin; // a / b (truediv)
	def HWTFPGA_FP_FREM: HwtFpgaFpBin; // a rem b (remainder)
	def HWTFPGA_FP_FMOD: HwtFpgaFpBin; // a % b (modulo)
	def HWTFPGA_FP_FDIVREM: HwtFpgaFpBinBinRes; // computes div and rem as dst0, dst1
	def HWTFPGA_FP_SHR: HwtFpgaFpBin; // a >> b, where b is int, translates to sub of exponent for FP / ashr for Q
	def HWTFPGA_FP_SHL: HwtFpgaFpBin; // a << b, same as HWTFPGA_FP_SHR just to left, add of exponent for FP/ shl for Q

	def HWTFPGA_FP_FCMP: HwtFpgaInst<
	    (outs type0:$dst),
	    (ins i64imm:$predicate, anyregcls:$src1, anyregcls:$src2,
		    // HFloatTmpConfig options
			i64imm:$isInQFormat,
		    i64imm:$exponentOrIntWidth,
			i64imm:$mantissaOrFracWidth,
			i64imm:$supportSubnormal,
			i64imm:$hasSign,
			i64imm:$hasIsNaN,
			i64imm:$hasIsInf,
			i64imm:$hasIs1,
			i64imm:$hasIs0,
		    i64imm:$rounding,
		    i64imm:$saturation),
	    []>;

	def HWTFPGA_FP_CEIL: HwtFpgaFpUn;
	def HWTFPGA_FP_COS: HwtFpgaFpUn;
	def HWTFPGA_FP_EXP: HwtFpgaFpUn;
	def HWTFPGA_FP_EXP10: HwtFpgaFpUn;
	def HWTFPGA_FP_EXP2: HwtFpgaFpUn;
	def HWTFPGA_FP_FABS: HwtFpgaFpUn;
	def HWTFPGA_FP_FLOOR: HwtFpgaFpUn;
	def HWTFPGA_FP_LOG: HwtFpgaFpUn;
	def HWTFPGA_FP_LOG2: HwtFpgaFpUn;
	def HWTFPGA_FP_LOG10: HwtFpgaFpUn;
	def HWTFPGA_FP_FPOW: HwtFpgaFpBin; // a ** b
	def HWTFPGA_FP_FPOWI: HwtFpgaFpBin; // a ** b (b is a signed integer)
	def HWTFPGA_FP_ROUND: HwtFpgaFpUn;
	def HWTFPGA_FP_ROUNDEVEN: HwtFpgaFpUn;
	def HWTFPGA_FP_SIN: HwtFpgaFpUn;
	def HWTFPGA_FP_SQRT: HwtFpgaFpUn;

    def HWTFPGA_FP_SINPI: HwtFpgaFpUn;
    def HWTFPGA_FP_COSPI: HwtFpgaFpUn;
    def HWTFPGA_FP_ASIN: HwtFpgaFpUn;
    def HWTFPGA_FP_SINH: HwtFpgaFpUn;
    def HWTFPGA_FP_ACOS: HwtFpgaFpUn;
    def HWTFPGA_FP_COSH: HwtFpgaFpUn;
    def HWTFPGA_FP_TAN: HwtFpgaFpUn;
    def HWTFPGA_FP_TANPI: HwtFpgaFpUn;
    def HWTFPGA_FP_ATAN: HwtFpgaFpUn;
    def HWTFPGA_FP_TANH: HwtFpgaFpUn;
    def HWTFPGA_FP_ATAN2: HwtFpgaFpBinBinRes;
    def HWTFPGA_FP_SINCOS: HwtFpgaFpUnBinRes;
    def HWTFPGA_FP_SINCOSPI: HwtFpgaFpUnBinRes;
    def HWTFPGA_FP_ASINCOS: HwtFpgaFpUnBinRes;
    def HWTFPGA_FP_SINCOSH: HwtFpgaFpUnBinRes;

	def HWTFPGA_FP_CAST: HwtFpgaInst<
	    (outs type0:$dst),
	    (ins anyregcls:$src, 
		    // src HFloatTmpConfig options
			i64imm:$srcIsInQFormat,
		    i64imm:$srcExponentOrIntWidth,
			i64imm:$srcMantissaOrFracWidth,
			i64imm:$srcSupportSubnormal,
			i64imm:$srcHasSign,
			i64imm:$srcHasIsNaN,
			i64imm:$srcHasIsInf,
			i64imm:$srcHasIs1,
			i64imm:$srcHasIs0,
		    i64imm:$srcRounding,
		    i64imm:$srcSaturation,
		    // dst HFloatTmpConfig options
			i64imm:$dstIsInQFormat,
		    i64imm:$dstExponentOrIntWidth,
			i64imm:$dstMantissaOrFracWidth,
			i64imm:$dstSupportSubnormal,
			i64imm:$dstHasSign,
			i64imm:$dstHasIsNaN,
			i64imm:$dstHasIsInf,
			i64imm:$dstHasIs1,
			i64imm:$dstHasIs0,
		    i64imm:$dstRounding,
		    i64imm:$dstSaturation
		    ),
	    []>;
}