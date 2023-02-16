#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy


class VariableChain(Unit):

    def _config(self) -> None:
        self.LEN = Param(3) 

    def _declr(self):
        addClkRstn(self)
        self.i = VectSignal(8, signed=False)
        self.o = VectSignal(8, signed=False)._m()

    def mainThread(self, hls: HlsScope):
        # :note: all variables are supposed to be reduced out and just direct connection should remain
        path = [hls.var(f"i{i}", self.i._dtype) for i in range(self.LEN)]
        while BIT.from_py(1):
            for i, p in enumerate(path):
                if i == 0:
                    prev = hls.read(self.i).data
                else:
                    prev = path[i - 1]
                p(prev)

            hls.write(path[-1], self.o)

    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = VariableChain()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
