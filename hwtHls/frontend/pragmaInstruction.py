from dis import Instruction
from typing import Optional, Tuple

from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.frame import PyBytecodeFrame
from hwtHls.frontend.indexExpansion import PyObjectRequiresExpandBeforeUse
from hwtHls.frontend.pragma import _PyBytecodeInstructionPragma, _PyBytecodeIntrinsic, \
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


class ThreadSplitContext():
    """
    Syntax sugar for PyBytecodeIntrinsicThreadSplitBegin/End
    
    :ivar asyncBegin: specifies if ordering with original section must be asserted
        or not, if asyncBegin and there is no data dependency then 1b dummy value is
        added (output from parent section, input to this extracted section)
    :ivar asyncEnd: equivalent of asyncBegin just for end (1b sync value is output of this extracted
        section and input to parent)
    :ivar aggregateInputs: specifies if all input variables should be concatenated into a single wide variable
        or if potentially many individual variables should be used to pass data between predecessor thread
        and this extracted section
    :ivar aggregateOutputs: equivalent of aggregateInputs for outputs
    """

    def __init__(self, name: str, asyncBegin=False, asyncEnd=False,
                 aggregateInputs=True, aggregateOutputs=True):
        self.name = name
        self.asyncBegin = asyncBegin
        self.asyncEnd = asyncEnd
        self.aggregateInputs = aggregateInputs
        self.aggregateOutputs = aggregateOutputs

    def begin(self):
        return PyBytecodeIntrinsicThreadSplitBegin(self.name, self.asyncBegin, self.aggregateInputs)

    def end(self):
        return PyBytecodeIntrinsicThreadSplitEnd(self.name, self.asyncEnd, self.aggregateOutputs)


class PyBytecodeIntrinsicThreadSplitBegin(_PyBytecodePragma):
    """
    Marks begin of section which should be extracted to a separate thread.
    This is useful in situations where sections of code have only dependencies which allows
    them to run concurrently or in pipeline like manner.
    
    * If this is inside of the loop, the section from this to latch (including) is extracted to a new thread.
    * The extracted code is removed from original code and the function will get new arguments to represent channels
      for communication with extracted code. New argument writes/reads will be used to pass data to and from new
      thread.
    * PHIs of parent loops are sinked if possible to reduce inter-thread communication.
    """

    def __init__(self, name: str, mayBecomeAsync: bool, aggregateIO: bool):
        self.name = name
        self.mayBecomeAsync = mayBecomeAsync
        self.aggregateIO = aggregateIO

    @override
    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction):
        return pyToSsa.toLlvm.b.CreateThreadSplitBegin(self.name, self.mayBecomeAsync, self.aggregateIO)


class PyBytecodeIntrinsicThreadSplitEnd(_PyBytecodePragma):

    def __init__(self, name: str, mayBecomeAsync: bool, aggregateIO: bool):
        PyBytecodeIntrinsicThreadSplitBegin.__init__(self, name, mayBecomeAsync, aggregateIO)

    @override
    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction):
        return pyToSsa.toLlvm.b.CreateThreadSplitEnd(self.name, self.mayBecomeAsync, self.aggregateIO)


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
