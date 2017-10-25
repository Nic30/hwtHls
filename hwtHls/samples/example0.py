from hwt.interfaces.std import VectSignal
from hwt.synthesizer.interfaceLevel.unit import Unit
from hwtHls.hls import Hls


class ExampleUnit(Unit):
    def _declr(self):
        self.a = VectSignal(32)
        self.b = VectSignal(32)
        self.c = VectSignal(32)
        self.d = VectSignal(32)
        self.e = VectSignal(32)

    def _impl(self):
        self.e(self.a + self.b + self.c + self.d)
        with Hls(freq=int(100e6)) as hls:
            r = hls.read
            e = (r(self.a) + r(self.b)) * (r(self.c) + r(self.d))
            hls.write(e, self.e)
