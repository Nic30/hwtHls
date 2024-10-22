from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


@hlsBytecode
def popcount(num: RtlSignal, bitsToLookupInROM: int=4, dbgRomInPyList=False):
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
        leftRes = PyBytecodeInline(popcount)(num[w // 2:], bitsToLookupInROM=bitsToLookupInROM, dbgRomInPyList=dbgRomInPyList)
        rightRes = PyBytecodeInline(popcount)(num[:w // 2], bitsToLookupInROM=bitsToLookupInROM, dbgRomInPyList=dbgRomInPyList)
        res = leftRes._reinterpret_cast(res._dtype) + rightRes._reinterpret_cast(res._dtype)

    return res


class Popcount(HwModule):

    @override
    def hwConfig(self) -> None:
        self.FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)
        self.BITS_TO_LOOKUP_IN_ROM = HwParam(4)
        self.DBG_ROM_IN_PYLIST = HwParam(False)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk._FREQ = self.FREQ
        w = self.DATA_WIDTH
        self.data_in = HwIOVectSignal(w)
        self.data_out = HwIOVectSignal(log2ceil(w + 1))._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            i = hls.read(self.data_in)
            hls.write(PyBytecodeInline(popcount)(i, bitsToLookupInROM=self.BITS_TO_LOOKUP_IN_ROM, dbgRomInPyList=self.DBG_ROM_IN_PYLIST), self.data_out)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    import sys

    sys.setrecursionlimit(int(1e6))
    m = Popcount()
    m.DATA_WIDTH = 64
    m.BITS_TO_LOOKUP_IN_ROM = 4

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
        debugFilter=HlsDebugBundle.ALL_RELIABLE,
        # llvmCliArgs=[("print-after-all", 0, "", "true"), ]
    )))

