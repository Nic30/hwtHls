# https://electronics.stackexchange.com/questions/196914/verilog-synthesize-high-speed-leading-zero-count
# https://content.sciendo.com/view/journals/jee/66/6/article-p329.xml?language=en
from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.mainBases import RtlSignalBase
from hwt.math import isPow2, log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from pyMathBitPrecise.bit_utils import mask


@hlsBytecode
def _countLeadingRecurse(dataIn: RtlSignalBase[HBits], bitValToCount: int):
    """
    Construct a balanced tree for counter of leading 0/1

    :atterntion: result is not final result, it is only for 0 to width-1 values

    """
    assert bitValToCount in (0, 1), bitValToCount
    inWidth = dataIn._dtype.bit_length()
    if inWidth == 2:
        if bitValToCount == 0:
            return ~dataIn[1]
        else:
            return dataIn[1]
    else:
        assert inWidth > 2, inWidth
        lhs = dataIn[:inWidth // 2]
        rhs = dataIn[inWidth // 2:]
        if bitValToCount == 0:
            leftFull = lhs._eq(0)
        else:
            leftFull = lhs._eq(mask(lhs._dtype.bit_length()))

        in_ = lhs._dtype.from_py(None)
        if leftFull:
            in_ = rhs
        else:
            in_ = lhs

        halfCount = PyBytecodeInline(_countLeadingRecurse)(in_, bitValToCount)
        return Concat(leftFull, halfCount)


@hlsBytecode
def _countTailingRecurse(dataIn: RtlSignalBase[HBits], bitValToCount: int):
    """
    Verison of :func:`~._countLeadingRecurse` which counts from the back of the vector (upper bits first)
    """
    assert bitValToCount in (0, 1), bitValToCount
    inWidth = dataIn._dtype.bit_length()
    if inWidth == 2:
        if bitValToCount == 0:
            return ~dataIn[0]
        else:
            return dataIn[0]
    else:
        assert inWidth > 2, inWidth
        lhs = dataIn[:inWidth // 2]
        rhs = dataIn[inWidth // 2:]
        if bitValToCount == 0:
            leftFull = rhs._eq(0)
        else:
            leftFull = rhs._eq(mask(rhs._dtype.bit_length()))

        in_ = rhs._dtype.from_py(None)
        if leftFull:
            in_ = lhs
        else:
            in_ = rhs

        halfCount = PyBytecodeInline(_countTailingRecurse)(in_, bitValToCount)
        return Concat(leftFull, halfCount)


@hlsBytecode
def countBits(dataIn: RtlSignalBase[HBits], bitValToCount: int, leading: bool):
    """
    :returns: number of bits set to value bitValToCount
    """
    inWidth = dataIn._dtype.bit_length()
    assert bitValToCount in (0, 1), bitValToCount
    assert isinstance(leading, bool), leading

    if bitValToCount == 0:
        full = dataIn._eq(0)
    else:
        full = dataIn._eq(mask(inWidth))

    halfCount = PyBytecodeInline(_countLeadingRecurse if leading else _countTailingRecurse)(dataIn, bitValToCount)
    dataOut = HBits(log2ceil(inWidth + 1)).from_py(None)
    if full:
        dataOut = inWidth
    else:
        dataOut = Concat(BIT.from_py(0), halfCount)

    return dataOut


class CountLeadingZeros(HwModule):

    @override
    def hwConfig(self) -> None:
        self.FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk._FREQ = self.FREQ
        w = self.DATA_WIDTH
        assert isPow2(self.DATA_WIDTH), self.DATA_WIDTH
        self.data_in = HwIOVectSignal(w)
        self.data_out = HwIOVectSignal(log2ceil(w + 1))._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            i = hls.read(self.data_in)
            hls.write(PyBytecodeInline(countBits)(i, 0, True), self.data_out)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class CountTailingZeros(CountLeadingZeros):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            i = hls.read(self.data_in)
            hls.write(PyBytecodeInline(countBits)(i, 0, False), self.data_out)


class CountLeadingOnes(CountLeadingZeros):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            i = hls.read(self.data_in)
            hls.write(PyBytecodeInline(countBits)(i, 1, True), self.data_out)


class CountTailingOnes(CountLeadingZeros):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            i = hls.read(self.data_in)
            hls.write(PyBytecodeInline(countBits)(i, 1, False), self.data_out)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    import sys

    sys.setrecursionlimit(int(1e6))
    m = CountLeadingZeros()
    m.DATA_WIDTH = 4

    print(to_rtl_str(m, target_platform=Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
