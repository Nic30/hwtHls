#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread
from hwtLib.types.ctypes import uint32_t, uint8_t


class HlsConnectionFromPyFn0(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            hls.write(hls.read(self.i), self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls))
        hls.compile()


class HlsConnectionFromPyFnTmpVar(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            v = hls.read(self.i)
            hls.write(v, self.o)


class HlsConnectionFromPyFnPreprocTmpVar0(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            o = self.o
            hls.write(hls.read(self.i), o)


class HlsConnectionFromPyFnPreprocTmpVar1(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        o = self.o
        while BIT.from_py(1):
            hls.write(hls.read(self.i), o)


class HlsConnectionFromPyFn1(Unit):

    def _declr(self):
        self.i = VectSignal(8 - 4, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            hls.write(Concat(hls.read(self.i), Bits(4).from_py(0)), self.o)

    def _impl(self):
        HlsConnectionFromPyFn0._impl(self)


class HlsConnectionFromPyFnIfTmpVar(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            a: uint32_t = hls.read(self.i)
            if a._eq(3):
                hls.write(10, self.o)
            else:
                hls.write(11, self.o)


class HlsConnectionFromPyFnIf(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            if hls.read(self.i)._eq(3):
                hls.write(10, self.o)
            else:
                hls.write(11, self.o)


class HlsConnectionFromPyFnIfIf(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            a = hls.read(self.i)
            if a._eq(3):
                if a._eq(4):
                    hls.write(10, self.o)
                elif a._eq(5):
                    hls.write(11, self.o)
                else:
                    hls.write(12, self.o)
            else:
                hls.write(13, self.o)


class HlsConnectionFromPyFnElif(HlsConnectionFromPyFn0):

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            a = hls.read(self.i)
            if a._eq(3):
                hls.write(10, self.o)
            elif a._eq(4):
                hls.write(11, self.o)
            else:
                hls.write(12, self.o)


class HlsConnectionFromPyFnWhile(HlsConnectionFromPyFn0):

    def _declr(self):
        HlsConnectionFromPyFn0._declr(self)
        addClkRstn(self)

    def mainThread(self, hls: HlsStreamProc):
        while BIT.from_py(1):
            v = uint8_t.from_py(0)
            i = uint8_t.from_py(0)
            while i < 3:
                v += hls.read(self.i)
                i += 1
            hls.write(v, self.o)


class HlsConnectionFromPyFnKwArgs(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc, kwArg=1):
        while BIT.from_py(1):
            hls.write(kwArg, self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls, kwArg=10))
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = HlsConnectionFromPyFnPreprocTmpVar1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
