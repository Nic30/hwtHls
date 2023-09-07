from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Signal, Handshaked
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


class HlsPythonHwWhile3(HlsPythonHwWhile2):

    def _declr(self):
        addClkRstn(self)
        self.i = Handshaked()
        self.o = Handshaked()._m()
        for i in (self.i, self.o):
            i.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            while BIT.from_py(1):
                r1 = hls.read(self.i)
                # dCroped = [d.data._reinterpret_cast(Bits(i * 8)) for i in range(1, self.DATA_WIDTH // 8)]
                if r1 != 1:
                    r2 = hls.read(self.i)
                    hls.write(r2, self.o)
                    if r2 != 2:
                        break
                else:
                    break

            hls.write(99, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = HlsPythonHwWhile3()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.DBG_FRONTEND)))

