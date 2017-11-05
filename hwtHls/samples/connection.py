from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwt.synthesizer.utils import toRtl
from hwtHls.hls import Hls
from hwtHls.platform.virtual import VirtualHlsPlatform


class HlsConnection(Unit):
    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.read(self.a)
            hls.write(a, self.b)


class HlsSlice(Unit):
    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(16, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.read(self.a)
            hls.write(a[16:], self.b)


class HlsSlice2(Unit):
    def _declr(self):
        self.a = VectSignal(16, signed=False)
        self.b = VectSignal(32, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            a = hls.read(self.a)
            hls.write(a, self.b[16:])
            hls.write(16, self.b[:16])


if __name__ == "__main__":
    # u = HlsConnection()
    # print(toRtl(u, targetPlatform=VirtualHlsPlatform()) + "\n")

    u = HlsSlice()
    print(toRtl(u, targetPlatform=VirtualHlsPlatform()))

    # u = HlsSlice2()
    # print(toRtl(u, targetPlatform=VirtualHlsPlatform()) + "\n")
