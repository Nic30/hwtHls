#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.interfaces.std import VectSignal, Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython import pyFunctionToSsa
from hwtLib.types.ctypes import uint8_t


class BitWidthReductionCmp2Values(Unit):

    def _declr(self):
        self.i = VectSignal(16, signed=False)
        self.o = VectSignal(16, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                i = hls.read(self.i)
                # 1. only bits [5:0] should be compared
                # and the cmp of other bits should be shared
                # 2. output mux should be only for lower 4 bits and the uper bits should be set to 0x001 as it is constant in all cases
                if i._eq(10):
                    hls.write(20, self.o)
                elif i._eq(11):
                    hls.write(25, self.o)
                else:
                    hls.write(26, self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class BitWidthReductionCmpReducible(Unit):

    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(8, signed=False)
        self.b = VectSignal(8, signed=False)
        self.eq = Signal()._m()
        self.eq_prefix_same = Signal()._m()
        self.eq_prefix_same_1 = Signal()._m()
        self.eq_prefix_0vs1 = Signal()._m()
        self.eq_prefix_0vsAll = Signal()._m()
        self.eq_prefix_sameInMiddle = Signal()._m()
        self.eq_prefix_differentInMiddle = Signal()._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(50e6))
 
        zero8b = uint8_t.from_py(0)
        one8b = uint8_t.from_py(1)
        all8b = uint8_t.from_py(0xff)

        def mainThread():
            while True:
                a = hls.read(self.a)
                b = hls.read(self.b)
                hls.write(a._eq(b), self.eq)
                hls.write(Concat(zero8b, a)._eq(Concat(zero8b, b)), self.eq_prefix_same)  # resolved as a==b
                hls.write(Concat(one8b, a)._eq(Concat(one8b, b)), self.eq_prefix_same_1)  # resolved as a==b
                hls.write(Concat(zero8b, a)._eq(Concat(one8b, b)), self.eq_prefix_0vs1)  # resolved as 0
                hls.write(Concat(zero8b, a)._eq(Concat(all8b, b)), self.eq_prefix_0vsAll)  # resolved as 0
                hls.write(Concat(a[:4], zero8b, a[4:])._eq(Concat(b[:4], zero8b, b[4:])), self.eq_prefix_sameInMiddle)  # resolved as a==b
                hls.write(Concat(a[:4], zero8b, a[4:])._eq(Concat(b[:4], all8b, b[4:])), self.eq_prefix_differentInMiddle)  # resolved as 0

        hls._thread(*pyFunctionToSsa(hls, mainThread))
   
        
if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = BitWidthReductionCmpReducible()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
