from typing import Any, Optional, Callable, Self

from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.typingFuture import override
from tests.io.bram.bramSimRam import BramSimRam
from tests.passTestIo import PassTestIoOut, errMsgFrormatter_ioName


class PassTestIoOutRam(PassTestIoOut):

    def __init__(self, dataRef: list[Any], wordWidth:int, wordCnt:int,
                 hasWeMask=False,
                 itemCntLimit:Optional[int]=None,
                 name:Optional[str]=None,
                 rtlPresetBeforeClk=True,
                 errMsgFormatter: Optional[Callable[[Self, list[HBitsConst], list[int]], Any]]=errMsgFrormatter_ioName,
                 randomizeControl=False,
                 ):
        super().__init__(dataRef, itemCntLimit=itemCntLimit, name=name,
                         rtlPresetBeforeClk=rtlPresetBeforeClk,
                         errMsgFormatter=errMsgFormatter,
                         randomizeControl=randomizeControl)
        self.hasWeMask = hasWeMask
        self.wordWidth = wordWidth
        self.wordCnt = wordCnt

    @staticmethod
    def _ramDictToPy(ramFromSim: dict[int, HBitsConst]) -> dict[int, tuple[int, int]]:
        return {k: (v.val, v.vld_mask) for k, v in ramFromSim.items()}

    @override
    def getForModel(self):
        # spawn empty data container for output data
        ramOut = BramSimRam(self.wordWidth, self.wordCnt, hasWeMask=self.hasWeMask)
        return ramOut

    def checkForLlvmIr(self, dataSim: BramSimRam):
        ram = self._ramDictToPy(dataSim.data)
        # print("")
        # print(refRam)
        # print(ram)

        # for _i, _d, _m in dataRamOut:
        #    i = int(_i)
        #    m = int(_m)
        #    mExpanded = byte_mask_to_bit_mask_int(m, _m._dtype.bit_length())
        #    d = _d.val & _d.vld_mask & mExpanded
        #    assert (_d.vld_mask & mExpanded) == mExpanded, (f"all bytes which are marked valid by mask must be valid {_d.vld_mask:x} {_d.vld_mask:x}")
        #    storeToRamMaskedByIndex(ram, i, d, mExpanded)

        # print("")
        # print(refRam)
        # print(ram)
        self.passTests.tc.assertDictEqual(ram, self.dataRef)

    def checkForRtl(self):
        oPort = self._getRtlDutPort()
        ramOut = oPort._ag.mem
        ram = self._ramDictToPy(ramOut)
        # print("")
        # print(refRam)
        # print(ram)

        # for _i, _d, _m in dataRamOut:
        #    i = int(_i)
        #    m = int(_m)
        #    mExpanded = byte_mask_to_bit_mask_int(m, _m._dtype.bit_length())
        #    d = _d.val & _d.vld_mask & mExpanded
        #    assert (_d.vld_mask & mExpanded) == mExpanded, (f"all bytes which are marked valid by mask must be valid {_d.vld_mask:x} {_d.vld_mask:x}")
        #    storeToRamMaskedByIndex(ram, i, d, mExpanded)

        # print("")
        # print(refRam)
        # print(ram)
        self.passTests.tc.assertDictEqual(ram, self.dataRef)

