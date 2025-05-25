from dis import Instruction
from types import FunctionType
from typing import Union

from hwt.hdl.const import HConst
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.pragma import _PyBytecodePragma
from hwtHls.llvm.llvmIr import Value, BasicBlock


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

    def __init__(self, ref: Union[Value, HConst, RtlSignal]):
        _PyBytecodePragma.__init__(self)
        self.ref = ref

    def __iter__(self):
        """
        Used in in UNPACK_SEQUENCE
        """
        for i in self.ref:
            yield PyBytecodeInPreproc(i)

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction):
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
        _PyBytecodePragma.__init__(self)
        self.ref = ref

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction):
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
        _PyBytecodePragma.__init__(self)
        self.name = name

    def apply(self, pyToSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: BasicBlock, instr: Instruction):
        pyToSsa.dbgTracer.log(("renaming block", curBlock.getName().str(), self.name))
        curBlock.setName(pyToSsa.toLlvm.strCtx.addTwine(self.name))


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

    def __init__(self, cond: Union[Value, HConst, RtlSignal]):
        _PyBytecodePragma.__init__(self)
        assert isinstance(cond, (Value, HConst, RtlSignal)), (cond, "Must be hardware evaluated expression otherwise this marker is useless")
        self.cond = cond


class PyBytecodePreprocHwCopy(_PyBytecodePragma):
    """
    Explicitly copy HW-evaluated value.
    """

    def __init__(self, v: Union[Value, HConst, RtlSignal]):
        _PyBytecodePragma.__init__(self)
        assert isinstance(v, (Value, HConst, RtlSignal)), (v, "Must be hardware evaluated expression otherwise this marker is useless")
        self.v = v

