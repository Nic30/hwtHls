from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal, HwIOSignal
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwt.pyUtils.typingFuture import override


class RedundantCmpGT(HwModule):

    @override
    def hwConfig(self) -> None:
        self.FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        self.i0 = HwIOVectSignal(8, signed=False)
        # self.i1 = HwIOVectSignal(8, signed=False)

        self.o = HwIOSignal()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            i0 = hls.read(self.i0)
            # i1 = hls.read(self.i1)

            hls.write((i0 > 1) | (i0 > 2), self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = RedundantCmpGT()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
