
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal, Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import int8_t


class HlsPythonReadNonBlocking(Unit):

    def _declr(self):
        addClkRstn(self)
        self.i = Handshaked()
        self.i.DATA_WIDTH = 1

        self.o = VectSignal(8, signed=True)._m()

    def mainThread(self, hls: HlsScope):
        cntr = int8_t.from_py(0)
        while BIT.from_py(1):
            if hls.read(self.i, blocking=False).valid:
                cntr += 1
            else:
                cntr -= 1
            hls.write(cntr, self.o)
            
    def _impl(self):
        hls = HlsScope(self, freq=int(100e6))
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    u = HlsPythonReadNonBlocking()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugDir="tmp")))
