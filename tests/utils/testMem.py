from typing import Optional

from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from tests.utils.testQueue import TestRead, TestIoWithName


class TestRomEarlyTypeCast(TestIoWithName):
    """
    Test model meant as a IoProxyAddressed mock.
    The data is stored as a list of HConst.
    """

    def __init__(self, data, WORD_T: HdlType, name: Optional[str]=None):
        TestIoWithName.__init__(self, name)
        self.data: list[HConst] = [WORD_T.from_py(d) for d in data]
        assert isinstance(WORD_T, HBits), WORD_T
        self.WORD_T = WORD_T

    def read(self, i: int):
        i = int(i)
        assert i >= 0 and i < len(self.data), i
        d = self.data[i]
        # charI = i // (charWidth ** 2)
        # charX = i % charWidth
        # charY = (i - charI * charWidth ** 2) // charWidth
        # print("reading ", i, d, "num:", charI, (charY, charX))
        return TestRead(d, b1)


class TestRomLazyTypeCast(TestIoWithName):
    """
    Unlike :class:`SimRomEarlyTypeCast` this stores data as a list of pythonic values
    and they are cast to HConst upon the read.
    """

    def __init__(self, data: list, WORD_T: HdlType, name: Optional[str]=None):
        TestIoWithName.__init__(self, name)
        self.data: list = data
        assert isinstance(WORD_T, HBits), WORD_T
        self.WORD_T = WORD_T

    def read(self, i: int):
        i = int(i)
        assert i >= 0 and i < len(self.data), i
        d = self.data[i]
        # charI = i // (charWidth ** 2)
        # charX = i % charWidth
        # charY = (i - charI * charWidth ** 2) // charWidth
        # print("reading ", i, d, "num:", charI, (charY, charX))
        return TestRead(d if isinstance(d, HConst) else self.WORD_T.from_py(d), b1)

    def __repr__(self):
        return TestIoWithName.__repr__(self)


class TestRamEarlyTypeCast(TestRomEarlyTypeCast):

    def write(self, i: int, val):
        i = int(i)
        assert i > 0 and i < len(self.data)
        if isinstance(val, HConst):
            val = val.to_py()

        self.data[i] = val


class TestRamLazyTypeCast(TestRomLazyTypeCast):

    def write(self, i: int, val):
        i = int(i)
        assert i >= 0 and i < len(self.data), i
        if not isinstance(val, HConst):
            val = toHVal(val, self.WORD_T)

        self.data[i] = val
