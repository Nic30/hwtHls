#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint32_t, uint8_t


class HlsConnectionFromPyFn0(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(hls.read(self.i).data, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(10e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class HlsConnectionFromPyFnTmpVar(HlsConnectionFromPyFn0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            v = hls.read(self.i).data
            hls.write(v, self.o)


class HlsConnectionFromPyFnPreprocTmpVar0(HlsConnectionFromPyFn0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            o = PyBytecodeInPreproc(self.o)
            hls.write(hls.read(self.i).data, o)


class HlsConnectionFromPyFnPreprocTmpVar1(HlsConnectionFromPyFn0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        o = PyBytecodeInPreproc(self.o)
        while BIT.from_py(1):
            hls.write(hls.read(self.i).data, o)


class HlsConnectionFromPyFn1(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8 - 4, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            hls.write(Concat(hls.read(self.i).data, HBits(4).from_py(0)), self.o)

    @override
    def hwImpl(self):
        HlsConnectionFromPyFn0.hwImpl(self)


class HlsConnectionFromPyFnIfTmpVar(HlsConnectionFromPyFn0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a: uint32_t = hls.read(self.i).data
            if a._eq(3):
                hls.write(10, self.o)
            else:
                hls.write(11, self.o)


class HlsConnectionFromPyFnIf(HlsConnectionFromPyFn0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            if hls.read(self.i).data._eq(3):
                hls.write(10, self.o)
            else:
                hls.write(11, self.o)


class HlsConnectionFromPyFnIfIf(HlsConnectionFromPyFn0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.i).data
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

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            a = hls.read(self.i).data
            if a._eq(3):
                hls.write(10, self.o)
            elif a._eq(4):
                hls.write(11, self.o)
            else:
                hls.write(12, self.o)


class HlsConnectionFromPyFnWhile(HlsConnectionFromPyFn0):

    @override
    def hwDeclr(self):
        HlsConnectionFromPyFn0.hwDeclr(self)
        addClkRstn(self)

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        while BIT.from_py(1):
            v = uint8_t.from_py(0)
            i = uint8_t.from_py(0)
            while i < 3:
                v += hls.read(self.i).data
                i += 1
            hls.write(v, self.o)


class HlsConnectionFromPyFnKwArgs(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope, kwArg=1):
        while BIT.from_py(1):
            hls.write(kwArg, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, kwArg=10))
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = HlsConnectionFromPyFnKwArgs()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
