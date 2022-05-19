//===----------------------------------------------------------------------===//
// GenericFpga Instruction list
// note that this is a list of special instructions and generic G_* instructions are inherited.
//===----------------------------------------------------------------------===//

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

let hasSideEffects = 0, isPredicable = 1, isAsCheapAsAMove = 1 in {
// conditional copy, pseudo instruction used before final combiner
def GENFPGA_CCOPY : GenFpgaInst<
    (outs AnyRegCls:$dst),
	(ins AnyRegCls:$src1, AnyRegCls:$cond),
	[]>;
}

let mayLoad = 0, mayStore = 0, hasSideEffects = 0, isPredicable = 1, isSelect = 1, isAsCheapAsAMove = 1  in {
// generic multiplexor - combines copy, select and phi to a single instructions
// which manages conditional copy driven by predicate or predecessor block
def GENFPGA_MUX : GenFpgaInst<
    (outs AnyRegCls:$dst),
	(ins variable_ops), // ins are variadic, in format (cond value)* value?; cond can be register, value or BB
	[]>; // no pattern because we match in C++
}

let mayLoad = 1, canFoldAsLoad=1, hasSideEffects = 0, isPredicable = 1, isNotDuplicable = 1 in {
// conditional load
def GENFPGA_CLOAD : GenFpgaInst<
    (outs AnyRegCls:$dst),
	(ins AnyRegCls:$addr, AnyRegCls:$cond),
	[]>; // no pattern because we match in C++
}

let mayLoad = 0, mayStore = 1, hasSideEffects = 0, isPredicable = 1, isNotDuplicable = 1 in {
// conditional load
def GENFPGA_CSTORE : GenFpgaInst<
    (outs),
	(ins AnyRegCls:$val, AnyRegCls:$addr, AnyRegCls:$cond),
	[]>; // no pattern because we match in C++
}


let isBarrier = 1, isReturn = 1, isTerminator = 1, isPseudo = 1, isCodeGenOnly = 1 in
def PseudoRET :  GenFpgaInst<(outs), (ins variable_ops), []>;


