

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwt.simulator.simTestCase import SimTestCase
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.threadFromPy import HlsThreadFromPy
from hwtHls.io.hwIoVectorized import HwIOStructVecRdVld, \
    HwIoProxyScalarVectorized
from hwtHls.platform.virtual import VirtualHlsPlatform
from hwtHls.scope import HlsScope
from hwtSimApi.utils import freq_to_period
from tests.baseIrMirRtlTC import BaseIrMirRtl_TC


class IoVectorizationWrite3x(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.o: HwIOStructVecRdVld = HwIOStructVecRdVld()._m()
        self.o.T = HBits(8)
        self.o.LANE_CNT = 3

    @hlsBytecode
    def mainThread(self, hls: HlsScope, o: HwIoProxyScalarVectorized):
        while b1:
            o.write(1)
            o.write(2)
            o.write(3)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        o = HwIoProxyScalarVectorized(hls, self.o, dtype=self.o.T)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, o))
        hls.compile()


class IoVectorizationWrite3xInferred(IoVectorizationWrite3x):
    """
    Variant of :class:`IoVectorizationWrite3x` where the LANE_CNT is infered from the user code
    """

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        oTmp = HwIOStructVecRdVld()
        oTmp.T = self.o.T
        oTmp._name = "oTmp"
        o = HwIoProxyScalarVectorized(hls, oTmp, dtype=self.o.T)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, o))
        hls.compile()
        assert oTmp.LANE_CNT == self.o.LANE_CNT
        self.o(oTmp)


class IoVectorizationStore_TC(SimTestCase):

    def _test_no_comb_loops(self):
        BaseIrMirRtl_TC._test_no_comb_loops(self)

    def _test_IoVectorizationWrite3x(self, dut: IoVectorizationWrite3x,
                               N=4, timeMultiplier=1):

        CLK_PERIOD = freq_to_period(dut.CLK_FREQ)
        self.compileSimAndStart(dut, target_platform=VirtualHlsPlatform())

        self.runSim(int(N * CLK_PERIOD * timeMultiplier))
        self._test_no_comb_loops()

        self.assertValSequenceEqual(dut.o._ag.data, [1, 2, 3, 1, 2, 3, 1, 2, 3, ])

    def test_IoVectorizationWrite3x(self):
        dut = IoVectorizationWrite3x()
        self._test_IoVectorizationWrite3x(dut)

    def test_IoVectorizationWrite3xInferred(self):
        dut = IoVectorizationWrite3xInferred()
        self._test_IoVectorizationWrite3x(dut)


if __name__ == "__main__":
    import unittest
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.debugBundle import LLVM_CLI_COMMON_OPTS

    m = IoVectorizationWrite3xInferred()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(
         # llvmCliArgs=[LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,],
         debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    testLoader = unittest.TestLoader()
    suite = testLoader.loadTestsFromTestCase(IoVectorizationStore_TC)
    # suite = unittest.TestSuite([IoVectorizationStore_TC("test_IoVectorizationWrite3x")])
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

