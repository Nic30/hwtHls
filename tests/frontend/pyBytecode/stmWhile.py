from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class HlsPythonHwWhile0(Unit):

    def _declr(self):
        addClkRstn(self)
        self.o = VectSignal(8, signed=False)._m()
        self.i_rst = Signal()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while BIT.from_py(1):  # recognized as HW loop because of type
            i += 1
            hls.write(i, self.o)
            if hls.read(self.i_rst).data:
                i = 0

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class HlsPythonHwWhile1(HlsPythonHwWhile0):

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while BIT.from_py(1):  # recognized as HW loop because of type
            while True:  # recognized as HW loop because of break condition
                hls.write(i, self.o)
                i += 1
                if hls.read(self.i_rst).data:
                    break

            i = 0


class HlsPythonHwWhile2(HlsPythonHwWhile0):

    def _declr(self):
        addClkRstn(self)
        self.o = VectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        i = uint8_t.from_py(0)
        while BIT.from_py(1):  # recognized as HW loop because of type
            if i <= 4:
                hls.write(i, self.o)
            elif i._eq(10):
                break
            i += 1

        while BIT.from_py(1):
            hls.write(0, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = HlsPythonHwWhile2()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

