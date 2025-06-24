from typing import Optional, Tuple, Sequence

from hwt.hdl.const import HConst
from hwt.hdl.types.arrayConst import HArrayRtlSignal
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.frame import PyBytecodeFrame
from hwtHls.frontend.fromPython import PyBytecodeToSsa
from hwtHls.frontend.hwIterator import HwIterator
from hwtHls.frontend import hwrange.hwrange
from hwtHls.llvm.llvmIr import Value, BasicBlock


class _hwenumerate_iterator(HwIterator):
    """
    :class:`HwIterator` object returned by :class:`hwenumerate`,
        functionality equivalent to python "enumerate" function, but this is HwIterator
    """

    def __init__(self, name: Optional[str], sequence: HArrayRtlSignal):
        self.name = name
        size = sequence._dtype.size
        self.addrIt = iter(hwrange(0, size, name=None if name is None else name + ".addrIt"))
        self.sequence = sequence
        #self.inductionVar: Optional[RtlSignal] = None

    def __next__(self):
        """
        :note: Used only if executed in python
        """
        assert isinstance(self.sequence, HConst), self.sequence
        i = self.addrIt.__next__()
        return i, self.sequence[i]

    @override
    def hwInit(self, toSsa: PyBytecodeToSsa, frame: PyBytecodeFrame, block: BasicBlock) -> BasicBlock:
        block = self.addrIt.hwInit(toSsa, frame, block)
        #elmTy = self.sequence._dtype.element_t
        #self.inductionVar = toSsa.hls.var(self.__class__.__name__ + ".v", self.sequence._dtype.element_t)
        #toLlvm: ToLlvmIrTranslator = toSsa.toLlvm
        # write initialization data to inductionVar
        #initUndef = toLlvm._translateExprHConst(block, elmTy.from_py(None))
        #toLlvm._variableInBlock_insertRedef(block, self.inductionVar, (), initUndef)
        return block

    @override
    def hwIterStepValue(self) -> RtlSignal:
        val = self.sequence[self.addrIt.hwIterStepValue()]
        return (self.addrIt.hwIterStepValue(), val)

    @override
    def hwBreakCondition(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, block: BasicBlock) -> Tuple[BasicBlock, Value]:
        return self.addrIt.hwBreakCondition(toSsa, frame, block)

    @override
    def hwStep(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, block: BasicBlock) -> BasicBlock:
        #toLlvm: ToLlvmIrTranslator = toSsa.toLlvm
        block = self.addrIt.hwStep(toSsa, frame, block)
        #_nextVal = self.sequence[self.addrIt.hwIterStepValue()]
        #block, nextVal = toLlvm._translateExprToLlvm(block, _nextVal)
        #toLlvm._variableInBlock_insertRedef(block, self.inductionVar, (), nextVal)
        return block


class hwenumerate():
    """
    Python enumetate() equivalent which is conversible to llvm (is not expanded during preprocessing)
    """

    def __init__(self, sequence: Sequence, name=None):
        self.sequence = sequence
        self.name = name

    def __iter__(self):
        return _hwenumerate_iterator(self.name, self.sequence)
