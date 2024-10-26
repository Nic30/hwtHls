from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitsCastUtils import fitTo_t
from hwt.hwIOs.std import HwIOVectSignal, HwIOClk
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.hwrange import hwrange
from hwtHls.frontend.pyBytecode.pragmaLoop import PyBytecodeLoopFlattenUsingIf
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period


class HlsPythonHwrange_fromInt0(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(HwIOClk.DEFAULT_FREQ)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        for i in hwrange(8):
            hls.write(fitTo_t(i, self.o._dtype), self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonHwrange_fromInt1(HlsPythonHwrange_fromInt0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            for i in hwrange(8):
                hls.write(fitTo_t(i, self.o._dtype), self.o)


class HlsPythonHwrange_fromInt2(HlsPythonHwrange_fromInt0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            for y in hwrange(4):
                for x in hwrange(4):
                    hls.write(fitTo_t(Concat(y[2:], x[2:]), self.o._dtype), self.o)
                    #PyBytecodeLoopFlattenUsingIf()


class HlsPythonHwrange_fromSsaVal(HlsPythonHwrange_fromInt0):

    @override
    def hwDeclr(self):
        super().hwDeclr()
        self.i = HwIOVectSignal(8, signed=False)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        r = hls.read(self.i).data
        for i in hwrange(r):
            hls.write(fitTo_t(i, self.o._dtype), self.o)


class HlsPythonHwrange_TC(SimTestCase):

    def test_HlsPythonHwrange_fromInt0(self, cls=HlsPythonHwrange_fromInt0,
                                      refRes=list(range(8)) + [7, 7, 7]):
        dut = cls()
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        CLK_PERIOD = freq_to_period(dut.clk.FREQ)
        self.runSim((len(refRes) + 1) * int(CLK_PERIOD))

        self.assertValSequenceEqual(dut.o._ag.data, refRes)

    def test_HlsPythonHwrange_fromInt1(self):
        self.test_HlsPythonHwrange_fromInt0(cls=HlsPythonHwrange_fromInt1,
                                            refRes=[i % 8 for i in range(15)])

    def test_HlsPythonHwrange_fromInt2(self):
        self.test_HlsPythonHwrange_fromInt0(cls=HlsPythonHwrange_fromInt2,
                                            refRes=[i % 0xf for i in range(15)])


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.platform import HlsDebugBundle

    m = HlsPythonHwrange_fromInt2()
    print(to_rtl_str(m, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsPythonHwrange_TC('test_HlsPythonHwrange_fromInt2')])
    suite = testLoader.loadTestsFromTestCase(HlsPythonHwrange_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

