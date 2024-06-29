#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Union

from hwt.code import Concat
from hwt.hdl.const import HConst
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal, HwIOSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t


class BitWidthReductionCmp2Values(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(16, signed=False)
        self.o = HwIOVectSignal(16, signed=False)._m()

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))

        @hlsBytecode
        def mainThread():
            PyBytecodeBlockLabel("entry")
            while BIT.from_py(1):
                PyBytecodeBlockLabel("loopHeader")
                i = hls.read(self.i).data
                # 1. only bits [5:0] should be compared
                # and the cmp of other bits should be shared
                # 2. output mux should be only for lower 4 bits and the upper bits should be set to 0x001 as it is constant in all cases
                if i._eq(10):
                    PyBytecodeBlockLabel("case10")
                    hls.write(20, self.o)
                elif i._eq(11):
                    PyBytecodeBlockLabel("case11")
                    hls.write(25, self.o)
                else:
                    PyBytecodeBlockLabel("caseElse")
                    hls.write(26, self.o)

        hls.addThread(HlsThreadFromPy(hls, mainThread))
        hls.compile()


class BitWidthReductionCmpReducibleEq(HwModule):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.a = HwIOVectSignal(8, signed=False)
        self.b = HwIOVectSignal(8, signed=False)
        self.res = HwIOSignal()._m()
        self.res_same = HwIOSignal()._m()
        self.res_prefix_same = HwIOSignal()._m()
        self.res_prefix_same_1 = HwIOSignal()._m()
        self.res_prefix_0vs1 = HwIOSignal()._m()
        self.res_prefix_0vsAll = HwIOSignal()._m()

        self.res_suffix_aVs0 = HwIOSignal()._m()
        self.res_suffix_aVsAll = HwIOSignal()._m()
        self.res_suffix_0vsB = HwIOSignal()._m()
        self.res_suffix_AllVsB = HwIOSignal()._m()

        self.res_prefix_aVs0 = HwIOSignal()._m()
        self.res_prefix_aVsAll = HwIOSignal()._m()
        self.res_prefix_bVs0 = HwIOSignal()._m()
        self.res_prefix_bVsAll = HwIOSignal()._m()
        
        self.res_prefix_sameInMiddle = HwIOSignal()._m()
        self.res_prefix_differentInMiddle = HwIOSignal()._m()

    def predicate(self, a:Union[RtlSignal, HConst], b:Union[RtlSignal, HConst]):
        return a._eq(b)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(50e6))

        zero8b = uint8_t.from_py(0)
        one8b = uint8_t.from_py(1)
        all8b = uint8_t.from_py(0xff)

        p = self.predicate

        @hlsBytecode
        def mainThread():
            PyBytecodeBlockLabel("entry")
            while BIT.from_py(1):
                PyBytecodeBlockLabel("loopHeader")
                a = hls.read(self.a).data
                b = hls.read(self.b).data
                hls.write(p(a, b), self.res)
                hls.write(p(a, a), self.res_same)
                hls.write(p(Concat(zero8b, a), Concat(zero8b, b)), self.res_prefix_same)  # resolved as a==b
                hls.write(p(Concat(one8b, a), Concat(one8b, b)), self.res_prefix_same_1)  # resolved as a==b
                hls.write(p(Concat(zero8b, a), Concat(one8b, b)), self.res_prefix_0vs1)  # resolved as 0
                hls.write(p(Concat(zero8b, a), Concat(all8b, b)), self.res_prefix_0vsAll)  # resolved as 0
                
                hls.write(p(Concat(a, a), Concat(zero8b, b)), self.res_suffix_aVs0)
                hls.write(p(Concat(a, a), Concat(all8b, b)), self.res_suffix_aVsAll)
                hls.write(p(Concat(zero8b, a), Concat(b, b)), self.res_suffix_0vsB)
                hls.write(p(Concat(all8b, a), Concat(b, b)), self.res_suffix_AllVsB)
                
                hls.write(p(Concat(a, a), Concat(b, zero8b)), self.res_prefix_aVs0)
                hls.write(p(Concat(a, a), Concat(b, all8b)), self.res_prefix_aVsAll)
                hls.write(p(Concat(a, zero8b), Concat(b, b)), self.res_prefix_bVs0)
                hls.write(p(Concat(a, all8b), Concat(b, b)), self.res_prefix_bVsAll)
                
                hls.write(p(Concat(a[:4], zero8b, a[4:]), Concat(b[:4], zero8b, b[4:])), self.res_prefix_sameInMiddle)  # resolved as a==b
                hls.write(p(Concat(a[:4], zero8b, a[4:]), Concat(b[:4], all8b, b[4:])), self.res_prefix_differentInMiddle)  # resolved as 0

        hls.addThread(HlsThreadFromPy(hls, mainThread))
        hls.compile()


class BitWidthReductionCmpReducibleNe(BitWidthReductionCmpReducibleEq):

    @override
    def predicate(self, a:Union[RtlSignal, HConst], b:Union[RtlSignal, HConst]):
        return a != b


class BitWidthReductionCmpReducibleLt(BitWidthReductionCmpReducibleEq):

    @override
    def predicate(self, a:Union[RtlSignal, HConst], b:Union[RtlSignal, HConst]):
        return a < b


class BitWidthReductionCmpReducibleLe(BitWidthReductionCmpReducibleEq):

    @override
    def predicate(self, a:Union[RtlSignal, HConst], b:Union[RtlSignal, HConst]):
        return a <= b


class BitWidthReductionCmpReducibleGt(BitWidthReductionCmpReducibleEq):

    @override
    def predicate(self, a:Union[RtlSignal, HConst], b:Union[RtlSignal, HConst]):
        return a > b


class BitWidthReductionCmpReducibleGe(BitWidthReductionCmpReducibleEq):

    @override
    def predicate(self, a:Union[RtlSignal, HConst], b:Union[RtlSignal, HConst]):
        return a >= b


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = BitWidthReductionCmpReducibleEq()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
