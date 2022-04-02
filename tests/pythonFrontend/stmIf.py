#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.fromPython import HlsStreamProcPyThread


class HlsConnectionFromPyIf(Unit):

    def _declr(self):
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()
        addClkRstn(self)

    def mainThread(self, hls: HlsStreamProc):
        v = hls.read(self.i)
        if v._eq(2):
            hls.write(3, self.o)

    def _impl(self):
        hls = HlsStreamProc(self)
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls))
        hls.compile()


class HlsConnectionFromPyIfElse(HlsConnectionFromPyIf):

    def mainThread(self, hls: HlsStreamProc):
        v = hls.read(self.i)
        if v._eq(2):
            hls.write(3, self.o)
        else:
            hls.write(10, self.o)


class HlsConnectionFromPyIfElsePreproc(HlsConnectionFromPyIf):

    def mainThread(self, hls: HlsStreamProc, useIf: bool):
        if useIf:
            v = hls.read(self.i)
            if v._eq(2):
                hls.write(3, self.o)
            else:
                hls.write(10, self.o)
        else:
            v = hls.read(self.i)
            hls.write(v, self.o)

    def _impl(self):
        hls = HlsStreamProc(self)
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls, True))
        hls.compile()


class HlsConnectionFromPyIfElifElse(HlsConnectionFromPyIf):

    def mainThread(self, hls: HlsStreamProc):
        v = hls.read(self.i)

        if v._eq(2):
            hls.write(3, self.o)
        elif v._eq(10):
            hls.write(11, self.o)
        else:
            hls.write(10, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = HlsConnectionFromPyIfElsePreproc()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
