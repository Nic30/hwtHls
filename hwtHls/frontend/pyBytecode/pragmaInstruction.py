from dis import Instruction
from typing import Optional, Tuple

from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.indexExpansion import PyObjectRequiresExpandBeforeUse
from hwtHls.frontend.pyBytecode.pragma import _PyBytecodeInstructionPragma, _PyBytecodeIntrinsic, \
    _PyBytecodePragma
from hwtHls.llvm.llvmIr import IRBuilder, Value, ValueToInstruction, BasicBlock, \
    OverflowingBinaryOperator
from hwtHls.netlist.hdlTypeVoid import HVoidData


class PyBytecodeNoSplitSlices(_PyBytecodeInstructionPragma):
    """
    Prevent SlicesToIndependentVariablesPass to split value on bits where it is cut by slices, trucats etc.
    """

    @override
    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", v: Value):
        inst = ValueToInstruction(v)
        assert inst, v
        inst.setMetadata(
            irTranslator.strCtx.addStringRef("hwtHls.slicesToIndependentVariables.noSplit"),
            irTranslator.mdGetTuple([], False))


class PyBytecodeIntrinsicAssume(_PyBytecodeIntrinsic):
    """
    Mark boolean expression as assumption about value.

    :see: https://llvm.org/docs/LangRef.html#llvm-assume-intrinsic
    
    example usage
    .. code-block::python
        PyBytecodeIntrinsicAssume()(x < 10)
    
    """

    def __init__(self, name: Optional[str]=None):
        assert name is None or isinstance(name, str), name
        super().__init__(BIT, HVoidData, name=name)

    @override
    def translateToLlvm(self, toLlvm: "ToLlvmIrTranslator", b: IRBuilder, args: Tuple[Value]):
        assert len(args) == 1, args
        return b.CreateAssumption(args[0])


class setHasNoUnsignedWrap(PyObjectRequiresExpandBeforeUse):
    """
    :see: corresponding function in llvm
    """

    def __init__(self, variable: RtlSignalBase, nuw=True):
        self.var = variable
        self.nuw = nuw

    def expandOnUse(self, toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
        curBlock, v = toSsa.toLlvm._translateExprToLlvm(curBlock, self.var)
        vI = ValueToInstruction(v)
        assert OverflowingBinaryOperator.classof(vI), ("Only appliable to OverflowingBinaryOperator instructions (Add, Sub, Mul, Shl)")
        vI.setHasNoUnsignedWrap(self.nuw)
        return curBlock, v


class setHasNoSignedWrap(PyObjectRequiresExpandBeforeUse):
    """
    :see: corresponding function in llvm
    """

    def __init__(self, variable: RtlSignalBase, nsw=True):
        self.var = variable
        self.nsw = nsw

    def expandOnUse(self, toSsa: "PyBytecodeToSsa",
                    offsetForLabels: int,
                    frame: PyBytecodeFrame, curBlock: BasicBlock) -> Tuple[BasicBlock, Value]:
        curBlock, v = toSsa.toLlvm._translateExprToLlvm(curBlock, self.var)
        vI = ValueToInstruction(v)
        assert OverflowingBinaryOperator.classof(vI), ("Only appliable to OverflowingBinaryOperator instructions (Add, Sub, Mul, Shl)")
        vI.setHasNoSignedWrap(self.nsw)
        return curBlock, v
