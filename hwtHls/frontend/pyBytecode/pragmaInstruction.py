from typing import Optional, Tuple

from hwt.hdl.types.defs import BIT
from hwtHls.frontend.pyBytecode.pragma import _PyBytecodeInstructionPragma, _PyBytecodeIntrinsic
from hwtHls.llvm.llvmIr import IRBuilder
from hwtHls.llvm.llvmIr import Value, ValueToInstruction
from hwtHls.netlist.hdlTypeVoid import HVoidData
from hwtHls.ssa.instr import SsaInstr


class PyBytecodeNoSplitSlices(_PyBytecodeInstructionPragma):
    """
    Prevent SlicesToIndependentVariablesPass to split value on bits where it is cut by slices, trucats etc.
    """

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", origInstr: SsaInstr, v: Value):
        inst = ValueToInstruction(v)
        assert inst, v
        inst.setMetadata(
            irTranslator.strCtx.addStringRef("hwtHls.slicesToIndependentVariables.noSplit"),
            irTranslator.mdGetTuple([], False))



class PyBytecodeIntrinsicAssume(_PyBytecodeIntrinsic):
    """
    Mark boolean expression as assumption about value.

    :see: https://llvm.org/docs/LangRef.html#llvm-assume-intrinsic
    """
    def __init__(self, name: Optional[str]=None):
        assert name is None or isinstance(name, str), name
        super().__init__(BIT, HVoidData, name=name)

    def translateToLlvm(self, b: IRBuilder, args: Tuple[Value]):
        assert len(args) == 1, args
        return b.CreateAssumption(args[0])
