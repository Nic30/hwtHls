from typing import Optional, Union, Tuple

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.memorySSAUpdater import MemorySSAUpdater
from hwtHls.frontend.pyBytecode.frame import PyBytecodeFrame
from hwtHls.frontend.pyBytecode.fromPython import PyBytecodeToSsa
from hwtHls.frontend.pyBytecode.hwIterator import HwIterator
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.exprBuilder import SsaExprBuilder
from hwtHls.ssa.value import SsaValue


class hwrange_iterator(HwIterator):

    def __init__(self, name: Optional[str],
                 start:Union[HBitsConst, SsaValue],
                 stop:Union[HBitsConst, SsaValue],
                 step:Union[HBitsConst, SsaValue], stepUsesAdd: bool):
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

    def _getValueOf(self, curBlock: SsaBasicBlock, m_ssa_u: MemorySSAUpdater, v: Union):
        if isinstance(v, (HBitsConst, SsaValue)):
            return v
        elif isinstance(v, RtlSignal):
            return m_ssa_u.readVariable(v, curBlock)
        else:
            raise ValueError(v)

    @override
    def hwInit(self, toSsa: PyBytecodeToSsa, frame: PyBytecodeFrame, curBlock: SsaBasicBlock) -> SsaBasicBlock:
        self.inductionVar = toSsa.hls.var(self.__class__.__name__ + ".i", self.start._dtype)
        m_ssa_u = toSsa.toSsa.m_ssa_u
        m_ssa_u.writeVariable(self.inductionVar, (), curBlock, self.start)
        return curBlock

    def hwIterStepValue(self):
        return self.inductionVar

    @override
    def hwCondition(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock) -> Tuple[SsaBasicBlock, SsaValue]:
        m_ssa_u = toSsa.toSsa.m_ssa_u
        v = m_ssa_u.readVariable(self.inductionVar, curBlock)
        b = SsaExprBuilder(curBlock)
        c = b._binaryOp(v, HwtOps.NE, self._getValueOf(curBlock, m_ssa_u, self.stop))
        return c, curBlock

    @override
    def hwStep(self, toSsa: "PyBytecodeToSsa", frame: PyBytecodeFrame, curBlock: SsaBasicBlock) -> SsaBasicBlock:
        m_ssa_u = toSsa.toSsa.m_ssa_u
        curVal = m_ssa_u.readVariable(self.inductionVar, curBlock)
        step = self._getValueOf(curBlock, m_ssa_u, self.step)
        b = SsaExprBuilder(curBlock)
        nextVal = b._binaryOp(curVal, HwtOps.ADD if self.stepUsesAdd else HwtOps.SUB, step)
        m_ssa_u.writeVariable(self.inductionVar, (), curBlock, nextVal)
        return curBlock


class hwrange():

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
