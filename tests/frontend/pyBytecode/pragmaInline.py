#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from hwtLib.types.ctypes import uint8_t
from hwt.interfaces.utils import addClkRstn


class PragmaInline_singleBlock(Unit):

    def _declr(self):
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):

        def fn():
            hls.write(1, self.o)

        while BIT.from_py(1):
            PyBytecodeInline(fn)()

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


class PragmaInline_NestedLoop(PragmaInline_singleBlock):

    def mainThread(self, hls: HlsScope):
        b1 = BIT.from_py(1)

        def fn():
            while b1:
                hls.write(1, self.o)

        while b1:
            PyBytecodeInline(fn)()


class PragmaInline_return1_0(PragmaInline_singleBlock):

    def mainThread(self, hls: HlsScope):

        def fn():
            return 1

        while BIT.from_py(1):
            hls.write(PyBytecodeInline(fn)(), self.o)


class PragmaInline_return1_1(PragmaInline_return1_0):

    def mainThread(self, hls: HlsScope):

        @PyBytecodeInline
        def fn():
            return 1

        while BIT.from_py(1):
            hls.write(fn(), self.o)


class PragmaInline_return1_1hw(PragmaInline_return1_0):

    def mainThread(self, hls: HlsScope):

        @PyBytecodeInline
        def fn():
            return uint8_t.from_py(1)

        while BIT.from_py(1):
            hls.write(fn(), self.o)


class PragmaInline_writeCntr0(PragmaInline_return1_0):

    def _declr(self):
        PragmaInline_return1_0._declr(self)
        addClkRstn(self)

    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        @PyBytecodeInline
        def fn(cntrArg):
            hls.write(cntrArg, self.o)

        while BIT.from_py(1):
            fn(cntr)
            cntr += 1


class PragmaInline_writeCntr1(PragmaInline_return1_0):

    def _declr(self):
        PragmaInline_return1_0._declr(self)
        addClkRstn(self)

    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        @PyBytecodeInline
        def fn(cntrArg):
            hls.write(cntrArg, self.o)
            cntrArg += 1

        while BIT.from_py(1):
            fn(cntr)


class PragmaInline_writeCntr2(PragmaInline_return1_0):

    def _declr(self):
        PragmaInline_return1_0._declr(self)
        addClkRstn(self)

    def mainThread(self, hls: HlsScope):
        cntr = uint8_t.from_py(0)

        @PyBytecodeInline
        def fn():
            nonlocal cntr
            hls.write(cntr, self.o)
            cntr += 1

        while BIT.from_py(1):
            fn()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = PragmaInline_writeCntr2()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))