#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.std import HwIOVectSignal, HwIOSignal
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class RedundantCmpGT(HwModule):

    @override
    def hwConfig(self) -> None:
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        self.i0 = HwIOVectSignal(8, signed=False)
        # self.i1 = HwIOVectSignal(8, signed=False)

        self.o = HwIOSignal()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            i0 = hls.read(self.i0).data
            # i1 = hls.read(self.i1)

            hls.write((i0 > 1) | (i0 > 2), self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = RedundantCmpGT()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
