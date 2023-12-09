//===----------------------------------------------------------------------===//
// HwtFpga Instruction list
// note that this is a list of special instructions and generic G_* instructions are inherited.
//===----------------------------------------------------------------------===//

// base class for HwtFpga instructions
class HwtFpgaInst<
             dag outs,
             dag ins,
             list<dag> pattern
             >
    : Instruction {
  let Namespace = "HwtFpga";
  dag OutOperandList = outs;
  dag InOperandList = ins;
  let Pattern = pattern;
}

class HwtFpgaBinOp : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins unknown:$src0, unknown:$src1),
    []>;

let hasSideEffects = 0, isAsCheapAsAMove = 1 in {
// an instruction which gets the argument of the function (used for IO of the circuit)
def HWTFPGA_ARG_GET : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins i64imm:$src),
    []> {
    	let hasSideEffects = true;
    }

// G_EXTRACT variant which have a number of extracted bits explicitely specified in last operand
def HWTFPGA_EXTRACT : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$src, i64imm:$offset, i64imm:$dstWidth),
    []>;

// G_MERGE_VALUES which have a number of concatenated bits explicitely specified
def HWTFPGA_MERGE_VALUES : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops), // specified in format anyregcls:$src{N}, i64imm:$width{N}, The input operands are always ordered from lowest bits to highest, (same as G_MERGE_VALUES)
                        // src operands does not have to be of same type which is difference between this and G_MERGE_VALUES
    []>;
}

let hasSideEffects = 0 in {
// bitwise inversion
def HWTFPGA_NOT : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$src),
    []>;
}


let mayLoad = 0, mayStore = 0, hasSideEffects = 0, isPredicable = 1, isSelect = 1, isAsCheapAsAMove = 1  in {
// generic multiplexor - combines copy, select and phi in to a single instructions
// which manages conditional copy/select driven by predicate or predecessor block
def HWTFPGA_MUX : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins variable_ops), // ins are variadic, in format (value cond)* value?;
                        // (format is same as for LLVM PHI) cond can be register, value or BB
                        // but in final optimized form cond it is only register or BB
                        // high bits first
    []>; // no pattern because we match in C++
}

let mayLoad = 1, canFoldAsLoad=1, hasSideEffects = 0, isPredicable = 0, isNotDuplicable = 1 in {
// conditional load if cond==1 else set $dst to undef with msb set to 0 
// :attention: this is not predicated instruction because dst is always modified
def HWTFPGA_CLOAD : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins anyregcls:$baseaddr, unknown: $index, unknown:$cond),
    []>; // no pattern because we match in C++
}

let mayLoad = 0, mayStore = 1, hasSideEffects = 0, isPredicable = 1, isNotDuplicable = 1 in {
// conditional store
def HWTFPGA_CSTORE : HwtFpgaInst<
    (outs),
    (ins anyregcls:$val, anyregcls:$addr, unknown: $index, unknown:$cond),
    []>; // no pattern because we match in C++
}

let isBarrier = 1, isReturn = 1, isTerminator = 1, isPseudo = 1, isCodeGenOnly = 1 in
def PseudoRET :  HwtFpgaInst<(outs), (ins variable_ops), []>;

// generic codes equivalents (llvm/Targets/GenericOpcodes.td)
// :attention: these codes are used only for final output so satisfy that the selected code does not contain
//  generic opcodes, however the generic opcodes are retained after selection until last step so it is possible
//  to use LLVM combiners
let isCommutable = 1, hasSideEffects = 0 in {
	def HWTFPGA_ADD : HwtFpgaBinOp;
	def HWTFPGA_AND : HwtFpgaBinOp;
	def HWTFPGA_OR : HwtFpgaBinOp;
	def HWTFPGA_XOR : HwtFpgaBinOp;
	def HWTFPGA_MUL : HwtFpgaBinOp;
}

let hasSideEffects = 0 in {
	def HWTFPGA_GLOBAL_VALUE : HwtFpgaInst<
	    (outs type0:$dst),
	    (ins unknown:$src),
	    []>;
	def HWTFPGA_UDIV : HwtFpgaBinOp;
	def HWTFPGA_SDIV : HwtFpgaBinOp;
	def HWTFPGA_UREM : HwtFpgaBinOp;
	def HWTFPGA_SREM : HwtFpgaBinOp;
	
	def HWTFPGA_SUB : HwtFpgaBinOp;
	def HWTFPGA_ICMP : HwtFpgaInst<
	    (outs type0:$dst),
	    (ins unknown:$tst, type1:$src1, type1:$src2),
	    []>;
}

def HWTFPGA_BR : HwtFpgaInst<
    (outs),
    (ins unknown:$dst_addr ),
    []> {
        let isBarrier = true;
        let hasSideEffects = false;
        let isBranch = true;
        let isTerminator = true;
    }

def HWTFPGA_BRCOND : HwtFpgaInst<
    (outs),
    (ins anyregcls:$cond, unknown:$dst_addr ),
    []> {
    	let hasSideEffects = false;
    	let isBranch = true;
    	let isTerminator = true;
    }

