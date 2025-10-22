from collections import deque
from math import inf
from typing import Sequence

from hwt.constants import NOP
from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr


class TestRead():

    def __init__(self, data, valid):
        self.data = data
        self.valid = valid


class TestInputQueue(deque):

    def __init__(self, T: HdlType, initData: Sequence[HConst]=(), maxNbReadsWithoutData=inf):
        super().__init__(initData)
        self.T = T
        self.nbReadsWithoutDataLimit = maxNbReadsWithoutData

    def read(self, blocking=True):
        if self:
            d = self.popleft()
            if d is NOP:
                assert not blocking, "This should be used only for non blocing reads"
            else:
                return TestRead(d, True)

        if blocking:
            raise SimIoUnderflowErr()
        else:
            if self.nbReadsWithoutDataLimit:
                if not self:
                    self.nbReadsWithoutDataLimit -= 1
                return TestRead(self.T.from_py(None), False)
            else:
                raise SimIoUnderflowErr()


class TestOutputIndexedQueue(deque):

    def write(self, index, data, mask=None):
        self.append((index, data, mask))

