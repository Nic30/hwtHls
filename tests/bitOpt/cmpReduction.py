from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Signal
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class RedundantCmpGT(Unit):

    def _config(self) -> None:
        self.FREQ = Param(int(100e6))

    def _declr(self):
        self.i0 = VectSignal(8, signed=False)
        # self.i1 = VectSignal(8, signed=False)

        self.o = Signal()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            i0 = hls.read(self.i0)
            # i1 = hls.read(self.i1)

            hls.write((i0 > 1) | (i0 > 2), self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = RedundantCmpGT()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

    # import unittest
    # suite = unittest.TestSuite()
    # # suite.addTest(AndShiftInLoop('test_AndShiftInLoop'))
    # suite.addTest(unittest.makeSuite(AndShiftInLoop_TC))
    # runner = unittest.TextTestRunner(verbosity=3)
    # runner.run(suite)
