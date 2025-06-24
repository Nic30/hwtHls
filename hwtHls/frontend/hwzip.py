from typing import Optional, Tuple, Sequence

from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.frame import PyBytecodeFrame
from hwtHls.frontend.fromPython import PyBytecodeToSsa
from hwtHls.frontend.hwIterator import HwIterator
from hwtHls.llvm.llvmIr import IRBuilder
from hwtHls.llvm.llvmIr import Value, BasicBlock


class _hwzip_iterator(HwIterator):
    """
    :class:`HwIterator` object returned by :class:`hwzip`,
        functionality equivalent to python "zip" function, but this is HwIterator

    """

    def __init__(self, name: Optional[str], iterators: tuple[HwIterator, ...]):
        assert isinstance(iterators, tuple), iterators
        for it in iterators:
            assert isinstance(it, HwIterator), it
        self.name = name
        self.iterators: tuple[HwIterator, ...] = iterators

    def __next__(self):
        """
        :note: Used only if executed in python
        """
        return tuple(next(it) for it in self.iterators)

    @override
    def hwInit(self, toSsa: PyBytecodeToSsa, frame: PyBytecodeFrame, block: BasicBlock) -> BasicBlock:
        for it in self.iterators:
            block = it.hwInit(toSsa, frame, block)
        return block

    @override
    def hwIterStepValue(self) -> RtlSignal:
        """
        :note: if this was zip_longest we would have to call hwIterStepValue only
            for those which did not return 1 from hwBreakCondition() yet.
        """
        return (it.hwIterStepValue() for it in self.iterators)

    @override
    def hwBreakCondition(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, block: BasicBlock) -> Tuple[BasicBlock, Value]:
        """
        If any sub iterator request break, break also in this iterator.
        """
        b: IRBuilder = toSsa.toLlvm.b
        cond = None
        for it in self.iterators:
            block, _cond = it.hwBreakCondition(toSsa, frame, block)
            assert _cond is not None
            if cond is None:
                cond = _cond
            else:
                cond = b.CreateOr(cond, _cond)

        return block, cond

    @override
    def hwStep(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, block: BasicBlock) -> BasicBlock:
        for it in self.iterators:
            block = it.hwStep(toSsa, frame, block)
        return block


class hwzip():
    """
    Python zip() equivalent which is conversible to llvm (is not expanded during preprocessing)
    """

    def __init__(self, *sequences: Sequence[Sequence], name=None):
        self.sequences = sequences
        self.name = name

    def __iter__(self):
        return _hwzip_iterator(self.name, self.sequences)

