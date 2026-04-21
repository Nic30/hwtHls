from collections import deque
from math import inf
from typing import Sequence, Optional

from hwt.constants import NOP
from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwtHls.ssa.analysis.llvmIrInterpretUtils import SimIoUnderflowErr, \
    SimIoOverflowErr


class TestIoWithName():
    """
    :ivar name: name for debugging purpose
    """

    def __init__(self, name: Optional[str]=None):
        self.name = name

    def __repr__(self):
        if self.name is None:
            return super().__repr__()
        else:
            return f"<{self.__class__.__name__:s} {self.name:s} 0x{id(self):016x}>"


class TestRead():
    """
    Mock type for testing which has the properties of HlsRead returned by :meth:`IoProxy.read`
    """

    def __init__(self, data, valid):
        self.data = data
        self.valid = valid


class TestQueueIn(deque):
    """
    Testing mock type for :class:`IoProxyScalar`. Implements a FIFO which supports read operation.
    """

    def __init__(self, T: HdlType, initData: Sequence[HConst]=(), maxNbReadsWithoutData=inf, name: Optional[str]=None):
        TestIoWithName.__init__(self, name)
        deque.__init__(self, initData)
        self.T = T
        self.nbReadsWithoutDataLimit = maxNbReadsWithoutData

    def read(self, blocking=True) -> HConst:
        if self:
            d = self.popleft()
            if d is NOP:
                assert not blocking, "This should be used only for non blocing reads"
            else:
                return TestRead(d, True)

        if blocking:
            raise SimIoUnderflowErr(self)
        else:
            if self.nbReadsWithoutDataLimit:
                if not self:
                    self.nbReadsWithoutDataLimit -= 1
                return TestRead(self.T.from_py(None), False)
            else:
                raise SimIoUnderflowErr(self)


class TestQueueOut(deque):
    """
    Testing mock type for :class:`IoProxyScalar`. Implements a FIFO which supports write operation.
    """

    def __init__(self, T: HdlType,
                 maxItemCnt: Optional[int], name: Optional[str]=None):
        deque.__init__(self)
        self.T = T
        self.name = name
        self.maxItemCnt = maxItemCnt

    def write(self, val: HConst):
        if self.maxItemCnt is not None and len(self) == self.maxItemCnt:
            raise SimIoOverflowErr(self)
        else:
            assert val._dtype == self.T, (self.T, val._dtype, val)
            self.append(val)


class TestQueueInOut(TestQueueIn):
    """
    Testing mock type for :class:`IoProxyScalar`. Implements a FIFO which supports read/write operation.
    """

    def __init__(self, T: HdlType,
                 maxItemCnt: Optional[int]=None,
                 initData: Sequence[HConst]=(),
                 maxNbReadsWithoutData=inf, name: Optional[str]=None):
        TestQueueIn.__init__(self, T, initData=initData, maxNbReadsWithoutData=maxNbReadsWithoutData, name=name)
        self.maxItemCnt = maxItemCnt

    def read(self, blocking=True) -> HConst:
        return TestQueueIn.read(self, blocking=blocking)

    def write(self, val: HConst):
        return TestQueueOut.write(self, val)


class TestQueueOutIndexed(deque):
    """
    Testing mock type for :class:`IoProxyScalar`. Implements a FIFO which stores tuples for store into array.
    """

    def write(self, index, data, mask=None):
        self.append((index, data, mask))

    def __repr__(self) -> str:
        return TestIoWithName.__repr__(self)
