#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class VariableChain(HwModule):

    def _config(self) -> None:
        self.LEN = HwParam(3)

    def _declr(self):
        addClkRstn(self)
        self.i = HwIOVectSignal(8, signed=False)
        self.o = HwIOVectSignal(8, signed=False)._m()

    @hlsBytecode
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
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = VariableChain()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
