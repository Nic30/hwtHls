#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal, HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import int8_t


class HlsPythonReadNonBlocking(HwModule):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.i = HwIODataRdVld()
        self.i.DATA_WIDTH = 1

        self.o = HwIOVectSignal(8, signed=True)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        cntr = int8_t.from_py(0)
        while BIT.from_py(1):
            if hls.read(self.i, blocking=False).valid:
                cntr += 1
            else:
                cntr -= 1
            hls.write(cntr, self.o)

    @override
    def hwImpl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle

    m = HlsPythonReadNonBlocking()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
