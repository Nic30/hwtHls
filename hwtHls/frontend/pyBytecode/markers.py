from dis import Instruction
from math import inf
from types import FunctionType
from typing import Union, Literal, List

from hwt.hdl.value import HValue
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.ioProxyStream import IoProxyStream
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo
from hwtHls.llvm.llvmIr import BranchInst, Argument, Function, Value, ValueToInstruction
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.ssa.instr import SsaInstr


class _PyBytecodePragma():

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        raise NotImplementedError()


class _PyBytecodeFunctionPragma(_PyBytecodePragma):

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        frame.pragma.append(self)


class _PyBytecodeLoopPragma(_PyBytecodePragma):
    """
    A type of pragma which is applied to a loop.
    """

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        assert frame.loopStack, "This pragma needs to be placed in the loop"
        loop: PyBytecodeLoopInfo = frame.loopStack[-1]
        loop.pragma.append(self)

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", brInst: BranchInst):
        raise NotImplementedError("This is abstract class override this method")


class PyBytecodeInstructionPragma(_PyBytecodePragma):

    def __init__(self, variable: Union["SsaInstr", RtlSignalBase]):
        self.varTmp = variable

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        # add self to metadata of reference variable
        v = pyToSsa.toSsa.m_ssa_u.readVariable(self.varTmp, curBlock)
        assert isinstance(v, SsaInstr), v
        if v.metadata is None:
            v.metadata = [self, ]
        else:
            v.metadata.append(self)

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", origInst: Instruction, v: Value):
        raise NotImplementedError("This is abstract class override this method")


class PyBytecodeInPreproc(_PyBytecodePragma):
    """
    A marker of hw object that the immediate store is store of preproc variable only.


    Usage:

    .. code-block:: Python


        x = PyBytecodeInPreproc(uint8_t.from_py(0))
        # x is now variable holding original uint8_t value no extraction
        #   to hardware was performed and x stays only in preprocessor
        # :note: it is sufficient to mark variable only once in first initialization
    """

    def __init__(self, ref: Union[SsaValue, HValue, RtlSignal]):
        self.ref = ref

    def __iter__(self):
        """
        Used in in UNPACK_SEQUENCE
        """
        for i in self.ref:
            yield PyBytecodeInPreproc(i)

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        pass


class PyBytecodeInline(_PyBytecodePragma):
    """
    Inline function body to a callsite in preprocessor.

    :attention: There is an interference with method bounding, do not use decorator for methods

    Usage:

    .. code-block:: Python

        PyBytecodeInline(fn)(args)

        # or

        @PyBytecodeInline
        def fn(args):
            pass

        fn(args)

    """

    def __init__(self, ref: FunctionType):
        self.ref = ref

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        pass

    def __call__(self, *args, **kwargs):
        return self.ref(*args, **kwargs)


class PyBytecodeBlockLabel(_PyBytecodePragma):
    """
    Set a specific name to a code block.

    Usage:

    .. code-block:: Python

        PyBytecodeInline("bb.0")

    """

    def __init__(self, name: str):
        self.name = name

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        pyToSsa.dbgTracer.log(("renaming block", curBlock.label, self.name))
        curBlock.label = self.name


class PyBytecodePreprocDivergence(_PyBytecodePragma):
    """
    Marks that the condition causes divergence in preprocessor and each dependent code blocks must be duplicated for each path.
    :note: required only for a divergence where value of preprocessor variables is resolved from HW evaluated condition
    Usage:

    .. code-block:: Python

        x = uint8_t.from_py(0) # variable realized in hardware
        if PyBytecodePreprocDivergence(x):
            i = 0
        else:
            i = 1
        use(i) # this code block will be duplicated for each possible value of i variable
               # without :class:`~.PyBytecodePreprocDivergence` the i variable would have only
               # value 0 because the successor blocks would be generated only for a first variant


    :note: required only for a divergence where value of preprocessor variables is resolved from HW evaluated condition

    """

    def __init__(self, cond: Union[SsaValue, HValue, RtlSignal]):
        assert isinstance(cond, (SsaValue, HValue, RtlSignal)), (cond, "Must be hardware evaluated expression otherwise this marker is useless")
        self.cond = cond


class PyBytecodePreprocHwCopy(_PyBytecodePragma):
    """
    Explicitly copy HW-evaluated value.
    """

    def __init__(self, v: Union[SsaValue, HValue, RtlSignal]):
        assert isinstance(v, (SsaValue, HValue, RtlSignal)), (v, "Must be hardware evaluated expression otherwise this marker is useless")
        self.v = v


class PyBytecodeLLVMLoopUnroll(_PyBytecodeLoopPragma):
    """
    https://releases.llvm.org/16.0.0/docs/LangRef.html#llvm-loop-unroll
    llvm/lib/Transforms/Utils/LoopUtils.cpp

    This adds llvm.loop.unroll pragma. For example:

    .. code-block:: llvm

        br i1 %exitcond, label %._crit_edge, label %.lr.ph, !llvm.loop !0
        ...
        !0 = !{!0, !1, !2}
        !1 = !{!"llvm.loop.unroll.enable"}
        !2 = !{!"llvm.loop.unroll.count", i32 4}
    """

    def __init__(self, enable: bool, count: Union[int, Literal[inf], None]):
        if not enable:
            if count == 1:
                count = None
            else:
                assert count is None, "If this is disable count must not be specified"

        self.enable = enable
        self.count = count

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", brInst: BranchInst):
        getStr = irTranslator.mdGetStr
        getInt = irTranslator.mdGetUInt32
        getTuple = irTranslator.mdGetTuple

        items = [
            getTuple([getStr("llvm.loop.unroll.enable" if self.enable else "llvm.loop.unroll.dissable"), ], False),
        ]
        if self.enable:
            count = self.count
            if count is not None:
                if count is inf:
                    md = getTuple([getStr("llvm.loop.unroll.full"), ], False)
                else:
                    md = getTuple([
                            getStr("llvm.loop.unroll.count"),
                            getInt(self.count)
                        ],
                        False)
                items.append(md)

        brInst.setMetadata(irTranslator.strCtx.addStringRef("llvm.loop"), getTuple(items, True))


class PyBytecodeStreamLoopUnroll(_PyBytecodeLoopPragma):
    """
    Unrolls the loop to meet IO throughput criteria.
    This adds hwthls.loop.streamunroll pragma. For example:

    .. code-block:: llvm

        br i1 %exitcond, label %._crit_edge, label %.lr.ph, !hwthls.loop !0
        ...
        !0 = !{!0, !1}
        !1 = !{!"hwthls.loop.streamunroll.unroll.io", i32 0}

    https://yashwantsingh.in/posts/loop-unroll/
    """

    def __init__(self, io_: Union[Interface, IoProxyStream]):
        self.io = io_

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", brInst: BranchInst):
        getStr = irTranslator.mdGetStr
        getInt = irTranslator.mdGetUInt32
        getTuple = irTranslator.mdGetTuple
        io_ = self.io
        if isinstance(io_, IoProxyStream):
            io_ = io_.interface
        ioArg: Argument = irTranslator.ioToVar[io_][0]
        ioArgIndex = ioArg.getArgNo();
        items = [getTuple([
                            getStr("hwthls.loop.streamunroll.io"),
                            getInt(ioArgIndex)
                        ],
                        False)
        ]
        brInst.setMetadata(irTranslator.strCtx.addStringRef("hwthls.loop"), getTuple(items, True))


class PyBytecodeSkipPass(_PyBytecodeFunctionPragma):
    """
    Skip pass by its name. For example:

    .. code-block:: llvm

        define void @main() !hwtHls.skipPass !0 {
        ...
        }
        !0 = !{!"hwtHls::SlicesToIndependentVariablesPass", !"ADCEPass"}
    """

    def __init__(self, skipedPassNames: List[str]):
        assert isinstance(skipedPassNames, (list, tuple)), skipedPassNames
        self.skipedPassNames = skipedPassNames

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", mainFn: Function):
        getStr = irTranslator.mdGetStr
        getTuple = irTranslator.mdGetTuple
        items = [getStr(passName) for passName in self.skipedPassNames]
        mainFn.setMetadata(irTranslator.strCtx.addStringRef("hwtHls.skipPass"), getTuple(items, False))


class PyBytecodeNoSplitSlices(PyBytecodeInstructionPragma):

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", origInst: Instruction, v: Value):
        inst = ValueToInstruction(v)
        assert inst, v
        inst.setMetadata(
            irTranslator.strCtx.addStringRef("hwtHls.slicesToIndependentVariables.noSplit"),
            irTranslator.mdGetTuple([], False))
