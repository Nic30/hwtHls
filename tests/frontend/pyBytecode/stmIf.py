#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class HlsConnectionFromPyIf(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()
        addClkRstn(self)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        v = hls.read(self.i).data
        if v._eq(2):
            hls.write(3, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class HlsConnectionFromPyIfElse(HlsConnectionFromPyIf):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        v = hls.read(self.i).data
        if v._eq(2):
            hls.write(3, self.o)
        else:
            hls.write(10, self.o)


class HlsConnectionFromPyIfElsePreproc(HlsConnectionFromPyIf):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope, useIf: bool):
        if useIf:
            v = hls.read(self.i).data
            if v._eq(2):
                hls.write(3, self.o)
            else:
                hls.write(10, self.o)
        else:
            v = hls.read(self.i).data
            hls.write(v, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, True))
        hls.compile()


class HlsConnectionFromPyIfElifElse(HlsConnectionFromPyIf):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        v = hls.read(self.i).data

        if v._eq(2):
            hls.write(3, self.o)
        elif v._eq(10):
            hls.write(11, self.o)
        else:
            hls.write(10, self.o)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = HlsConnectionFromPyIfElsePreproc()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
