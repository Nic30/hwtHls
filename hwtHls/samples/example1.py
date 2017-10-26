from hwt.interfaces.std import VectSignal
from hwt.synthesizer.interfaceLevel.unit import Unit
from hwtHls.hls import Hls
from hwt.synthesizer.shortcuts import toRtl


class HlsExample1(Unit):
    def _declr(self):
        self.a = VectSignal(32, signed=False)
        self.b = VectSignal(32, signed=False)
        self.c = VectSignal(32, signed=False)
        self.d = VectSignal(32, signed=False)
        self.e = VectSignal(32, signed=False)

    def _impl(self):
        with Hls(self, freq=int(100e6)) as hls:
            r = hls.read
            aPlusB = r(self.a) + r(self.b)
            cPlusD = r(self.c) + r(self.d)
            e = aPlusB * cPlusD
            hls.write(e, self.e)


if __name__ == "__main__":
    u = HlsExample1()
    print(toRtl(u))
