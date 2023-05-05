#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode import hlsBytecode


class ReadAtleastOneOf2(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i0 = Handshaked()
            self.i1 = Handshaked()

            self.o: Handshaked = Handshaked()._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):

        pre = PyBytecodeInPreproc
        while BIT.from_py(1):
            o = self.o.data._dtype.from_py(None)

            i0 = pre(hls.read(self.i0, blocking=False))
            if i0.valid:
                o = i0.data
            else:
                o = hls.read(self.i1)

            hls.write(o, self.o)

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


class ReadAtleastOneOf3(ReadAtleastOneOf2):

    def _declr(self):
        ReadAtleastOneOf2._declr(self)
        with self._paramsShared():
            self.i2 = Handshaked()

    def mainThread(self, hls: HlsScope):

        prepr = PyBytecodeInPreproc
        while BIT.from_py(1):
            o = self.o.data._dtype.from_py(None)

            i0 = prepr(hls.read(self.i0, blocking=False))
            if i0.valid:
                o = i0.data
            else:
                i1 = prepr(hls.read(self.i1, blocking=False))
                if i1.valid:
                    o = i1.data
                else:
                    o = hls.read(self.i2)

            hls.write(o, self.o)


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.platform import HlsDebugBundle
    u = ReadAtleastOneOf3()
    # u.CLK_FREQ = int(100e6)
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

