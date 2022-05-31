#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Union

from hwt.code import Concat
from hwt.hdl.value import HValue
from hwt.interfaces.std import VectSignal, Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread
from hwtLib.types.ctypes import uint8_t
from hwt.hdl.types.defs import BIT


class BitWidthReductionCmp2Values(Unit):

    def _declr(self):
        self.i = VectSignal(16, signed=False)
        self.o = VectSignal(16, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while BIT.from_py(1):
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

        hls.thread(HlsStreamProcPyThread(hls, mainThread))
        hls.compile()


class BitWidthReductionCmpReducibleEq(Unit):

    def _declr(self):
        addClkRstn(self)
        self.a = VectSignal(8, signed=False)
        self.b = VectSignal(8, signed=False)
        self.res = Signal()._m()
        self.res_same = Signal()._m()
        self.res_prefix_same = Signal()._m()
        self.res_prefix_same_1 = Signal()._m()
        self.res_prefix_0vs1 = Signal()._m()
        self.res_prefix_0vsAll = Signal()._m()
        self.res_prefix_sameInMiddle = Signal()._m()
        self.res_prefix_differentInMiddle = Signal()._m()

    def predicate(self, a:Union[RtlSignal, HValue], b:Union[RtlSignal, HValue]):
        return a._eq(b)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(50e6))
 
        zero8b = uint8_t.from_py(0)
        one8b = uint8_t.from_py(1)
        all8b = uint8_t.from_py(0xff)

        p = self.predicate

        def mainThread():
            while BIT.from_py(1):
                a = hls.read(self.a)
                b = hls.read(self.b)
                hls.write(p(a, b), self.res)
                hls.write(p(a, a), self.res_same)
                hls.write(p(Concat(zero8b, a), Concat(zero8b, b)), self.res_prefix_same)  # resolved as a==b
                hls.write(p(Concat(one8b, a), Concat(one8b, b)), self.res_prefix_same_1)  # resolved as a==b
                hls.write(p(Concat(zero8b, a), Concat(one8b, b)), self.res_prefix_0vs1)  # resolved as 0
                hls.write(p(Concat(zero8b, a), Concat(all8b, b)), self.res_prefix_0vsAll)  # resolved as 0
                hls.write(p(Concat(a[:4], zero8b, a[4:]), Concat(b[:4], zero8b, b[4:])), self.res_prefix_sameInMiddle)  # resolved as a==b
                hls.write(p(Concat(a[:4], zero8b, a[4:]), Concat(b[:4], all8b, b[4:])), self.res_prefix_differentInMiddle)  # resolved as 0

        hls.thread(HlsStreamProcPyThread(hls, mainThread))
        hls.compile()


class BitWidthReductionCmpReducibleNe(BitWidthReductionCmpReducibleEq):

    def predicate(self, a:Union[RtlSignal, HValue], b:Union[RtlSignal, HValue]):
        return a != b


class BitWidthReductionCmpReducibleLt(BitWidthReductionCmpReducibleEq):

    def predicate(self, a:Union[RtlSignal, HValue], b:Union[RtlSignal, HValue]):
        return a < b


class BitWidthReductionCmpReducibleLe(BitWidthReductionCmpReducibleEq):

    def predicate(self, a:Union[RtlSignal, HValue], b:Union[RtlSignal, HValue]):
        return a <= b


class BitWidthReductionCmpReducibleGt(BitWidthReductionCmpReducibleEq):

    def predicate(self, a:Union[RtlSignal, HValue], b:Union[RtlSignal, HValue]):
        return a > b


class BitWidthReductionCmpReducibleGe(BitWidthReductionCmpReducibleEq):

    def predicate(self, a:Union[RtlSignal, HValue], b:Union[RtlSignal, HValue]):
        return a >= b


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = BitWidthReductionCmpReducibleEq()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
