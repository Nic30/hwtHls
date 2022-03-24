#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.fromPython import pyFunctionToSsa
from hwtLib.types.ctypes import uint32_t
from hwtHls.platform.xilinx.artix7 import Artix7Medium


class Rom(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(2, signed=False)
        self.o = VectSignal(32, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        # must be hw type otherwise we won't be able to resolve type of o
        mem = [uint32_t.from_py(1 << i) for i in range(4)]
        while BIT.from_py(1):
            i = hls.read(self.i)
            o = mem[i]
            hls.write(o, self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls._thread(*pyFunctionToSsa(hls, self.mainThread, hls))


class CntrArray(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(2, signed=False)

        self.o_addr = VectSignal(2, signed=False)
        self.o = VectSignal(32, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        mem = [hls.var(f"v{i:d}", uint32_t) for i in range(4)]
        for v in mem:
            v(0) # we are using () instead of = because v is preproc variable

        while BIT.from_py(1):
            o = mem[hls.read(self.o_addr)]
            hls.write(o, self.o)
            i = hls.read(self.i)
            mem[i] += 1

    def _impl(self):
        Rom._impl(self)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = CntrArray()
    print(to_rtl_str(u, target_platform=Artix7Medium(**makeDebugPasses("tmp"))))
