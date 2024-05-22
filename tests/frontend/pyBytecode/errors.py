#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwt.pyUtils.typingFuture import override


class ErrorUseOfUnitialized0(HwModule):

    @override
    def hwDeclr(self):
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        res = a < 1
        while BIT.from_py(1):
            hls.write(hls.read(self.i).data, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class ErrorUseOfUnitialized1(ErrorUseOfUnitialized0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        res = a < 1
        a = 1
        while BIT.from_py(1):
            hls.write(res, self.o)


class UseOfNone(ErrorUseOfUnitialized0):

    @hlsBytecode
    @override
    def mainThread(self, hls: HlsScope):
        a = None
        while BIT.from_py(1):
            hls.write(a is None, self.o)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    m = UseOfNone()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
