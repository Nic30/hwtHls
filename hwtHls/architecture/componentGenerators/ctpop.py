#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.serializer.mode import serializeParamsUniq
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.architecture.componentGenerators.baseALU1HwModule import _BaseALU1HwModule


@hlsBytecode
def ctpop_fn(num: RtlSignal, bitsToLookupInROM: int=4, dbgRomInPyList=False):
    """
    Dalalah, A., Baba, S.E., & Tubaishat, A. (2006). New hardware architecture for bit-counting.
    http://fpgacpu.ca/fpga/Population_Count.html

    :param num: number to perform population count on
    :param bitsToLookupInROM: if number of bits is smaller than this number the computation
        is performed by ROM instead of adder
    """
    w = num._dtype.bit_length()
    res = HBits(log2ceil(w + 1)).from_py(None)
    if w == 1:
        res = num
    elif w <= bitsToLookupInROM:
        itemT = res._dtype
        # :note: this is not ideal as the ROM is constructed many times during recursion
        #   and then it must be recognized from CFG that this is a ROM and then that it has same value as other instances
        popcountRom = [itemT.from_py(i.bit_count()) for i in range(1 << w)]
        if not dbgRomInPyList:
            popcountRom = itemT[len(popcountRom)].from_py(popcountRom)
        res = popcountRom[num]
    else:
        leftRes = PyBytecodeInline(ctpop_fn)(num[w // 2:], bitsToLookupInROM=bitsToLookupInROM, dbgRomInPyList=dbgRomInPyList)
        rightRes = PyBytecodeInline(ctpop_fn)(num[:w // 2], bitsToLookupInROM=bitsToLookupInROM, dbgRomInPyList=dbgRomInPyList)
        res = leftRes._reinterpret_cast(res._dtype) + rightRes._reinterpret_cast(res._dtype)

    return res


@serializeParamsUniq
class Ctpop(_BaseALU1HwModule):

    @override
    def hwConfig(self) -> None:
        super().hwConfig()
        self.BITS_TO_LOOKUP_IN_ROM = HwParam(4)
        self.DBG_ROM_IN_PYLIST = HwParam(False)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        t = self.T
        assert isinstance(t, HBits), (t, self)
        self._addDataInDataOut(t, HBits(log2ceil(t.bit_length() + 1)))

    @hlsBytecode
    def aluFn(self, inp):
        return PyBytecodeInline(ctpop_fn)(
            inp,
            bitsToLookupInROM=self.BITS_TO_LOOKUP_IN_ROM,
            dbgRomInPyList=self.DBG_ROM_IN_PYLIST)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    import sys

    sys.setrecursionlimit(int(1e6))
    m = Ctpop()
    m.T = HBits(64)
    m.BITS_TO_LOOKUP_IN_ROM = 4

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[("print-after-all", 0, "", "true"), ]
    )))

