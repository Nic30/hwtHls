#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class FnClosureSingleItem(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):

        # closure is (hls, )
        def read(a):
            return hls.read(a).data

        while BIT.from_py(1):
            hls.write(read(self.i), self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class FnClosureNone0(Unit):

    def _declr(self):
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):

        def genVal():
            return 10

        while BIT.from_py(1):
            hls.write(genVal(), self.o)

    def _impl(self):
        FnClosureSingleItem._impl(self)


class FnClosureNone1(Unit):

    def _declr(self):
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):

        while BIT.from_py(1):

            def genVal():
                return 10

            hls.write(genVal(), self.o)

    def _impl(self):
        FnClosureSingleItem._impl(self)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = FnClosureNone1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
