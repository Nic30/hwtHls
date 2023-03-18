//===----------------------------------------------------------------------===//
// GenericFpga Instruction list
// note that this is a list of special instructions and generic G_* instructions are inherited.
//===----------------------------------------------------------------------===//

// base class for GenFpga instructions
class GenFpgaInst<
             dag outs,
             dag ins,
             list<dag> pattern
             >
    : Instruction {
  let Namespace = "GenericFpga";
  dag OutOperandList = outs;
  dag InOperandList = ins;
  let Pattern = pattern;
}

let hasSideEffects = 0, isAsCheapAsAMove = 1 in {
// an instruction which gets the argument of the function (used for IO of the circuit)
def GENFPGA_ARG_GET : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins i64imm:$src),
    []>;

// G_EXTRACT variant which have bumber of extracted bits explicitely specified in last operand
def GENFPGA_EXTRACT : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins AnyRegCls:$src, i64imm:$offset, i64imm:$dstWidth),
    []>;

def GENFPGA_MERGE_VALUES : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins variable_ops), // specified in format AnyRegCls:$src{N}, i64imm:$width{N}, The input operands are always ordered from lowest bits to highest, (same as G_MERGE_VALUES)
                        // src operands does not have to be of same type which is difference between this and G_MERGE_VALUES
    []>;
}

let hasSideEffects = 0 in {
// bitwise inversion
def GENFPGA_NOT : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins AnyRegCls:$src),
    []>;
}

let hasSideEffects = 0, isPredicable = 1, isAsCheapAsAMove = 1 in {
// conditional copy, pseudo instruction used before final combiner (which converts this to GENFPGA_MUX)
def GENFPGA_CCOPY : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins AnyRegCls:$src, AnyRegCls:$cond),
    []>;
}

let mayLoad = 0, mayStore = 0, hasSideEffects = 0, isPredicable = 1, isSelect = 1, isAsCheapAsAMove = 1  in {
// generic multiplexor - combines copy, select and phi in to a single instructions
// which manages conditional copy/select driven by predicate or predecessor block
def GENFPGA_MUX : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins variable_ops), // ins are variadic, in format (value cond)* value?;
                        // (format is same as for LLVM PHI) cond can be register, value or BB
                        // but in final optimized form cond it is only register or BB
                        // high bits first
    []>; // no pattern because we match in C++
}

let mayLoad = 1, canFoldAsLoad=1, hasSideEffects = 0, isPredicable = 1, isNotDuplicable = 1 in {
// conditional load
def GENFPGA_CLOAD : GenFpgaInst<
    (outs AnyRegCls:$dst),
    (ins AnyRegCls:$baseaddr, AnyRegCls: $index, AnyRegCls:$cond),
    []>; // no pattern because we match in C++
}

let mayLoad = 0, mayStore = 1, hasSideEffects = 0, isPredicable = 1, isNotDuplicable = 1 in {
// conditional store
def GENFPGA_CSTORE : GenFpgaInst<
    (outs),
    (ins AnyRegCls:$val, AnyRegCls:$addr, AnyRegCls: $index, AnyRegCls:$cond),
    []>; // no pattern because we match in C++
}

let isBarrier = 1, isReturn = 1, isTerminator = 1, isPseudo = 1, isCodeGenOnly = 1 in
def PseudoRET :  GenFpgaInst<(outs), (ins variable_ops), []>;
