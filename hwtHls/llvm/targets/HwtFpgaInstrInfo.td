//===----------------------------------------------------------------------===//
// HwtFpga Instruction list
// note that this is a list of special instructions and generic G_* instructions are inherited.
//===----------------------------------------------------------------------===//

// base class for HwtFpga instructions, for full option list :see: Instruction definition at llvm/Target/Target.td
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

class HwtFpgaUnOp : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins unknown:$src),
    []>;

class HwtFpgaBinOp : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins unknown:$src0, unknown:$src1),
    []>;

// an instruction which gets the argument of the function (used for IO of the circuit)
def HWTFPGA_ARG_GET : HwtFpgaInst<
    (outs anyregcls:$dst),
    (ins i64imm:$src),
    []> {
    	let hasSideEffects = true;
		let isAsCheapAsAMove = true;
    }

let hasSideEffects = 0, isAsCheapAsAMove = 1 in {

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
	def HWTFPGA_NOT : HwtFpgaUnOp;
	
	def HWTFPGA_GLOBAL_VALUE : HwtFpgaInst<
	    (outs type0:$dst),
	    (ins unknown:$src),
	    []>;
	def HWTFPGA_UDIV : HwtFpgaBinOp;
	def HWTFPGA_SDIV : HwtFpgaBinOp;
	def HWTFPGA_UREM : HwtFpgaBinOp;
	def HWTFPGA_SREM : HwtFpgaBinOp;

	def HWTFPGA_SHL : HwtFpgaBinOp;
	def HWTFPGA_LSHR : HwtFpgaBinOp;
	def HWTFPGA_ASHR : HwtFpgaBinOp;
	
	def HWTFPGA_SUB : HwtFpgaBinOp;
	def HWTFPGA_ICMP : HwtFpgaInst<
	    (outs type0:$dst),
	    (ins unknown:$tst, type1:$src1, type1:$src2),
	    []>;
	// https://llvm.org/docs/GlobalISel/GenericOpcode.html#g-ctlz-zero-undef-g-cttz-zero-undef
	def HWTFPGA_CTLZ_ZERO_UNDEF : HwtFpgaUnOp;
	def HWTFPGA_CTTZ_ZERO_UNDEF : HwtFpgaUnOp;
	// https://llvm.org/docs/GlobalISel/GenericOpcode.html#g-ctlz-g-cttz-g-ctpop
	def HWTFPGA_CTLZ : HwtFpgaUnOp;
	def HWTFPGA_CTTZ : HwtFpgaUnOp;
	def HWTFPGA_CTPOP : HwtFpgaUnOp;
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
// return from a function, if this is a top function the whole circuit execution is halted
def HWTFPGA_RET : HwtFpgaInst<(outs), (ins variable_ops), []> {
	let isBarrier = 1;
	let isReturn = 1;
	let isTerminator = 1;
}

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

// Execute code asynchronously.
// :param isAsyncBegin: If 1 the begin of callee is executed asynchonously (always, out of CFG) and this instruction waits for return
//                      Calle has no liveins from this code locations and it may have liveouts to this code location.
//                      If 0 the callee is executed asynchronously from this instruction and the execution does not wait for callee.
//                      Calle may have liveins from this code location and it has no liveouts.
// :param callee_addr: Block to be called.
def HWTFPGA_ASYNC_CALL : HwtFpgaInst<
    (outs),
    (ins anyregcls:$isAsyncBegin, unknown:$callee_addr),
    []> {
    	let hasSideEffects = true;
    }

include "HwtFpgaInstrInfoPyObjectPlaceholder.td"
include "HwtFpgaInstrInfoFP.td"


