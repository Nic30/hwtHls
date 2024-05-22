#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class FnClosureSingleItem(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):

        # closure is (hls, )
        def read(a):
            return hls.read(a).data

        while BIT.from_py(1):
            hls.write(read(self.i), self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class FnClosureNone0(HwModule):

    @override
    def hwDeclr(self):
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):

        def genVal():
            return 10

        while BIT.from_py(1):
            hls.write(genVal(), self.o)

    @override
    def hwImpl(self):
        FnClosureSingleItem.hwImpl(self)


class FnClosureNone1(HwModule):

    @override
    def hwDeclr(self):
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):

        while BIT.from_py(1):

            def genVal():
                return 10

            hls.write(genVal(), self.o)

    @override
    def hwImpl(self):
        FnClosureSingleItem.hwImpl(self)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = FnClosureNone1()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
