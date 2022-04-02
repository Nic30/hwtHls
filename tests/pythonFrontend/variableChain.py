#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.fromPython import pyFunctionToSsa


class VariableChain(Unit):

    def _config(self) -> None:
        self.LEN = Param(3) 

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        path = [hls.var(f"i{i}", self.i._dtype) for i in range(self.LEN)]
        while BIT.from_py(1):
            for i, p in enumerate(path):
                if i == 0:
                    prev = hls.read(self.i)
                else:
                    prev = path[i - 1]
                p(prev)

            hls.write(path[-1], self.o)

    def _impl(self):
        hls = HlsStreamProc(self, freq=int(100e6))
        hls._thread(*pyFunctionToSsa(hls, self.mainThread, hls))
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import makeDebugPasses, VirtualHlsPlatform
    u = VariableChain()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))
