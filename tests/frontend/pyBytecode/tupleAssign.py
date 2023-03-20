from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodePreprocHwCopy
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.baseSsaTest import BaseSsaTC


class HlsPythonTupleAssign(Unit):

    def _declr(self):
        addClkRstn(self)
        self.o0 = VectSignal(8)._m()
        self.o1 = VectSignal(8)._m()

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

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonTupleAssign_TC(BaseSsaTC):
    __FILE__ = __file__

    def test_HlsPythonTupleAssign_ll(self):
        self._test_ll(HlsPythonTupleAssign)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = HlsPythonTupleAssign()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    import unittest

    suite = unittest.TestSuite()
    # suite.addTest(PyArrHwIndex_TC('test_frameHeader'))
    suite.addTest(unittest.makeSuite(HlsPythonTupleAssign_TC))
    runner = unittest.TextTestRunner(verbosity=3)
    runner.run(suite)

