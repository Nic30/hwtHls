from typing import Optional, Union

from hwt.hdl.commonConstants import b1
from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.typeCast import toHVal
from hwt.hwIOs.agents.bramPort import storeToRamMaskedByAddress
from hwt.math import log2ceil
from pyMathBitPrecise.bit_utils import byte_mask_to_bit_mask_int, mask
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


class TestReadRam(TestRead):
    """
    Mock type for testing which has the properties of HlsRead returned by :meth:`IoProxy.IoProxyAddressed`
    """

    class TestReadRamData():
        """
        :note: this exists because the IoProxyAddressed read returns
            a struct which contains other thins than just data (e.g. error, id)
        """

        def __init__(self, data):
            self.data = data

    def __init__(self, data, valid):
        super().__init__(self.TestReadRamData(data), valid)


class TestRam(dict[int, Union[tuple[int, int], HBitsConst]], TestIoWithName):
    """
    Testing mock type for :class:`IoProxyArray`. Implements a ram/rom.
    
    :ivar _useHBits: switch between int tuple (data, mask) and HBitsConst implementation
    :ivar _addrStep: specifies how many bits 1 unit of address adresses
    """

    def __init__(self, wordTy: HBits, indexWidth: int, addrStep=8, useHBits=False, name=None):
        super().__init__()
        self._wordTy = wordTy
        self._wordInvalid = wordTy.from_py(None)
        self._addrStep = addrStep
        dataWidth = wordTy.bit_length()
        self._addrAlignBits = log2ceil(dataWidth // self._addrStep)
        self._useHBits = useHBits
        self._bitmask_all = mask(dataWidth)
        self._bitmask_allHTy = wordTy.from_py(self._bitmask_all)
        self.name = name
        self.indexT = HBits(indexWidth)
        self.addrLimit = mask(indexWidth)

    def read(self, addr: Union[int, HBitsConst], dtype:Optional[HBits]=None) -> TestReadRam:
        if isinstance(addr, int):
            assert addr < self.addrLimit, (addr, self.addrLimit, self.indexT)
        else:
            assert addr._dtype.bit_length() <= self.indexT.bit_length()
            if addr._is_full_valid():
                addr = int(addr)
            else:
                return TestRead(self._wordInvalid, b1)

        wordAlignAddrBitCnt = self._addrAlignBits
        alignShift = addr & mask(wordAlignAddrBitCnt)
        if alignShift != 0:
            raise NotImplementedError(addr, self._addrAlignBits)
        addr = addr >> wordAlignAddrBitCnt

        word = self.get(addr)
        if word is None:
            word = self._wordInvalid
        elif self._useHBits:
            assert isinstance(word, HConst), word
        else:
            val, vld = word[0], word[1]
            word = self._wordTy.from_py(val, vld)

        if dtype is not None:
            word = word._reinterpret_cast(dtype)
        return TestReadRam(word, b1)

    def write(self, addr: Union[int, HBitsConst], data: Union[int, HBitsConst], mask: Union[int, HBitsConst, None]=None):
        if isinstance(addr, int):
            assert addr < self.addrLimit, (addr, self.addrLimit, self.indexT)
        else:
            assert addr._dtype.bit_length() <= self.indexT.bit_length()
            if addr._is_full_valid():
                addr = int(addr)
            else:
                # write to invalid address causing invalidation of whole ram
                self.clear()
                return

        if mask is None:
            if self._useHBits:
                bitmask = self._bitmask_allHTy
            else:
                bitmask = self._bitmask_all
        else:
            mask = int(mask)
            bitmask = byte_mask_to_bit_mask_int(mask, self._addrStep)
            if not self._useHBits:
                bitmask = self._wordTy.from_py(bitmask)
        if self._useHBits:
            if isinstance(data, int):
                data = self._wordTy.from_py(data)
        else:
            assert isinstance(data, int), data

        storeToRamMaskedByAddress(self, addr, self._addrAlignBits, data, bitmask, isInHBits=self._useHBits)

    def __repr__(self) -> str:
        return TestIoWithName.__repr__(self)
