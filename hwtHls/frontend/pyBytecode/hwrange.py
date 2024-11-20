from typing import Optional, Union, Tuple

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.fromPython import PyBytecodeToSsa
from hwtHls.frontend.pyBytecode.hwIterator import HwIterator
from hwtHls.llvm.llvmIr import Value, BasicBlock
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class hwrange_iterator(HwIterator):
    """
    :class:`HwIterator` object returned by :class:`hwrange`
    """

    def __init__(self, name: Optional[str],
                 start:Union[HBitsConst, Value],
                 stop:Union[HBitsConst, Value],
                 step:Union[HBitsConst, Value], stepUsesAdd: bool):
        self.name = name
        self.start = start
        self.stop = stop
        self.step = step
        self.stepUsesAdd = stepUsesAdd
        self.inductionVar: Optional[RtlSignal] = None

    def __next__(self):
        """
        Used only if executed in python
        """
        start = self.start
        stop = self.stop
        assert isinstance(start, HBitsConst), start
        assert isinstance(stop, HBitsConst), stop
        if start == stop:
            raise StopIteration()

        step = self.step
        assert isinstance(step, HBitsConst), step
        if self.stepUsesAdd:
            self.start = start + step
        else:
            self.start = start - step

        return start

    @override
    def hwInit(self, toSsa: PyBytecodeToSsa, frame: PyBytecodeFrame, block: BasicBlock) -> BasicBlock:
        self.inductionVar = toSsa.hls.var(self.__class__.__name__ + ".i", self.start._dtype)
        toLlvm: ToLlvmIrTranslator = toSsa.toLlvm
        # write initialization data to inductionVar
        block, start = toLlvm._translateExprToLlvm(block, self.start)
        toLlvm._variableInBlock_insertRedef(block, self.inductionVar, (), start)
        return block

    @override
    def hwIterStepValue(self) -> RtlSignal:
        return self.inductionVar

    @override
    def hwCondition(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, block: BasicBlock) -> Tuple[BasicBlock, Value]:
        assert self.inductionVar is not None, ("This HwIterator should have been initialized during GET_ITER")
        toLlvm: ToLlvmIrTranslator = toSsa.toLlvm
        block, v = toLlvm._translateExprToLlvm(block, self.inductionVar)
        block, stop = toLlvm._translateExprToLlvm(block, self.stop)
        c = toLlvm.b.CreateICmpNE(v, stop, toLlvm.strCtx.addTwine("hwrange.continue"))
        return c, block

    @override
    def hwStep(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, block: BasicBlock) -> BasicBlock:
        toLlvm: ToLlvmIrTranslator = toSsa.toLlvm
        block, curVal = toLlvm._translateExprToLlvm(block, self.inductionVar)
        block, step = toLlvm._translateExprToLlvm(block, self.step)
        if self.stepUsesAdd:
            nextVal = toLlvm.b.CreateAdd(curVal, step)
        else:
            nextVal = toLlvm.b.CreateSub(curVal, step)

        toLlvm._variableInBlock_insertRedef(block, self.inductionVar, (), nextVal)
        return block


class hwrange():
    """
    Python range() equivalent which is conversible to llvm (is not expanded during preprocessing)
    """

    def __init__(self, start, stop=None, step=1, name=None):
        if stop is None:
            # normalize hwrange(8) to hwrange(0, 8)
            stop = start
            start = 0

        # try resolve type from
        dtype = None
        for v in (start, stop, step):
            dtype = getattr(v, "_dtype", None)
            if dtype is not None:
                assert isinstance(dtype, HBits), ("Must be a numeric type", dtype, v)
                break

        stepUsesAdd = True
        if dtype is None:
            # try resolve type from integer range
            for v in (start, stop, step):
                assert isinstance(v, int), (start, stop, step)

            signed = False
            if start < 0:
                signed = True
                w = log2ceil(-start + 1) + 1
            else:
                w = log2ceil(start + 1)

            if stop < 0:
                signed = True
                if start >= 0:
                    w += 1
                w = max(w, log2ceil(-stop + 1) + 1)
            else:
                w = max(w, log2ceil(stop + 1))

            if step < 1:
                stepUsesAdd = False
                step = -step
            dtype = HBits(w, signed)

        if isinstance(start, int):
            start = dtype.from_py(start)
        if isinstance(stop, int):
            stop = dtype.from_py(stop)
        if isinstance(step, int):
            step = dtype.from_py(step)

        self.start = start
        self.stop = stop
        self.step = step
        self.stepUsesAdd = stepUsesAdd
        self.name = name

    def __iter__(self):
        return hwrange_iterator(self.name, self.start, self.stop, self.step, self.stepUsesAdd)
