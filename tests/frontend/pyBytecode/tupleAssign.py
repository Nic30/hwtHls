from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodePreprocHwCopy
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.baseSsaTest import BaseSsaTC


class HlsPythonTupleAssign(HwModule):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.o0 = HwIOVectSignal(8)._m()
        self.o1 = HwIOVectSignal(8)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i0 = uint8_t.from_py(0)
        i1 = uint8_t.from_py(1)

        while BIT.from_py(1):
            hls.write(i0, self.o0)
            hls.write(i1, self.o1)
            # i0, i1 = i0, i1
            copy = PyBytecodePreprocHwCopy
            i1, i0 = copy(i0), copy(i1)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonTupleAssign_TC(BaseSsaTC):
    __FILE__ = __file__
    TEST_THREADS_AND_SYNC = False

    def test_HlsPythonTupleAssign_ll(self):
        self._test_ll(HlsPythonTupleAssign)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = HlsPythonTupleAssign()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    testLoader = unittest.TestLoader()
    # suite = unittest.TestSuite([HlsPythonTupleAssign_TC("test_frameHeader")])
    suite = testLoader.loadTestsFromTestCase(HlsPythonTupleAssign_TC)
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

