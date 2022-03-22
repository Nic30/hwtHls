#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.fromPython import pyFunctionToSsa


class FnClosureSingleItem(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):

        # closure is (hls, )
        def read(a):
            return hls.read(a)

        while BIT.from_py(1):
            hls.write(read(self.i), self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls._thread(*pyFunctionToSsa(hls, self.mainThread, hls))


class FnClosureNone0(Unit):

    def _declr(self):
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):

        def genVal():
            return 10

        while BIT.from_py(1):
            hls.write(genVal(), self.o)

    def _impl(self):
        FnClosureSingleItem._impl(self)


class FnClosureNone1(Unit):

    def _declr(self):
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):

        while BIT.from_py(1):

            def genVal():
                return 10

            hls.write(genVal(), self.o)

    def _impl(self):
        FnClosureSingleItem._impl(self)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = FnClosureNone1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
