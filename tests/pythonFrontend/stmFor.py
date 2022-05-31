#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.synthesizer.unit import Unit
from hwt.interfaces.std import VectSignal
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread
from hwt.interfaces.utils import addClkRstn


class HlsPythonPreprocFor(Unit):

    def _declr(self):
        addClkRstn(self)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        for i in range(5):
            hls.write(i, self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls))
        hls.compile()


class HlsPythonPreprocForPreprocWhile(HlsPythonPreprocFor):

    def mainThread(self, hls: HlsStreamProc):
        for i in range(5):
            while i < 2:
                hls.write(i, self.o)
                i += 1


class HlsPythonPreprocFor2x_0(HlsPythonPreprocFor):

    def mainThread(self, hls: HlsStreamProc):
        for y in range(2):
            for x in range(2):
                hls.write((y << 1) | x, self.o)


class HlsPythonPreprocFor2x_1(HlsPythonPreprocFor):

    def mainThread(self, hls: HlsStreamProc):
        for y in range(2):
            for _ in range(2):
                hls.write(y << 1, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = HlsPythonPreprocFor2x_1()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
