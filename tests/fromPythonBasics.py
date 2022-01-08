#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython import pyFunctionToSsa
from hwtLib.types.ctypes import uint32_t, uint8_t


class HlsConnectionFromPyFn0(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                hls.write(hls.read(self.i), self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFn1(Unit):

    def _declr(self):
        self.i = VectSignal(8 - 4, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                hls.write(Concat(hls.read(self.i), Bits(4).from_py(0)), self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnTmpVar(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                a: uint32_t = hls.read(self.i)
                if a == 3:
                    hls.write(10, self.o)
                else:
                    hls.write(11, self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnIf(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                if hls.read(self.i) == 3:
                    hls.write(10, self.o)
                else:
                    hls.write(11, self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnIfIf(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                a = hls.read(self.i)
                if a == 3:
                    if a == 4:
                        hls.write(10, self.o)
                    elif a == 5:
                        hls.write(11, self.o)
                else:
                    hls.write(12, self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnElif(HlsConnectionFromPyFn0):

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                a = hls.read(self.i)
                if a == 3:
                    hls.write(10, self.o)
                elif a == 4:
                    hls.write(11, self.o)
                else:
                    hls.write(12, self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


class HlsConnectionFromPyFnWhile(HlsConnectionFromPyFn0):

    def _declr(self):
        HlsConnectionFromPyFn0._declr(self)
        addClkRstn(self)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
 
        def mainThread():
            while True:
                v = uint8_t.from_py(0)
                i = uint8_t.from_py(0)
                while i < 3:
                    v += hls.read(self.i)
                    i += 1
                hls.write(v, self.o)

        hls._thread(*pyFunctionToSsa(hls, mainThread))


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = HlsConnectionFromPyFnWhile()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
