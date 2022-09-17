#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class ErrorUseOfUnitialized0(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):
        res = a < 1 
        while BIT.from_py(1):
            hls.write(hls.read(self.i).data, self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class ErrorUseOfUnitialized1(ErrorUseOfUnitialized0):

    def mainThread(self, hls: HlsScope):
        res = a < 1 
        a = 1
        while BIT.from_py(1):
            hls.write(res, self.o)


class UseOfNone(ErrorUseOfUnitialized0):

    def mainThread(self, hls: HlsScope):
        a = None
        while BIT.from_py(1):
            hls.write(a is None, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = UseOfNone()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
