from dis import Instruction
from math import inf
from types import FunctionType
from typing import Union, Optional, Literal

from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.loopMeta import PyBytecodeLoopInfo
from hwtHls.llvm.llvmIr import BranchInst, MDNode, ConstantAsMetadata, MDString
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.value import SsaValue
from hwtLib.types.ctypes import uint32_t


class _PyBytecodePragma():

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        raise NotImplementedError()


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
    Inline function body to a callsite.

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


class _PyBytecodeLoopPragma(_PyBytecodePragma):
    """
    A type of pragma which is applied to a loop.
    """

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock, instr: Instruction):
        assert frame.loopStack, "This pragma needs to be placed in the loop"
        loop: PyBytecodeLoopInfo = frame.loopStack[-1]
        loop.pragma.append(self)


class PyBytecodePipeline(_PyBytecodeLoopPragma):
    """
    Cancel the ordering between io on end->begin control transitions of the loop.
    Which results in a loop where operations can overlap with a previous iteration.
    """


class PyBytecodeLLVMLoopUnroll(_PyBytecodeLoopPragma):
    """
    https://releases.llvm.org/14.0.0/docs/LangRef.html#id1587

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
            assert count is None, "If this is dissable count must not be specified"

        self.enable = enable
        self.count = count

    def toLlvm(self, irTranslator: "ToLlvmIrTranslator", brInst: BranchInst):

        def getStr(s: str):
            return MDString.get(irTranslator.ctx, irTranslator.strCtx.addStringRef(s))

        def getInt(i: int):
            return ConstantAsMetadata.getConstant(irTranslator._translateExprInt(i, irTranslator._translateType(uint32_t)))

        def getTuple(items, insertSelfAsFirts):
            itemsAsMetadata = [i.asMetadata() for i in items]
            res = MDNode.get(irTranslator.ctx, itemsAsMetadata, insertTmpAsFirts=insertSelfAsFirts)
            if insertSelfAsFirts:
                res.replaceOperandWith(0, res.asMetadata())
            return res
        
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
   
