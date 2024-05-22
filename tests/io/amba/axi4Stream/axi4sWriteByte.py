#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.ctypes import uint8_t


class Axi4SWriteByteOnce(HwModule):

    def hwConfig(self):
        self.CLK_FREQ = HwParam(int(100e6))
        Axi4Stream.hwConfig(self)

    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.dataOut = Axi4Stream()._m()

    @hlsBytecode
    def mainThread(self, dataOut: IoProxyAxi4Stream):
        dataOut.writeStartOfFrame()
        dataOut.write(uint8_t.from_py(1))
        dataOut.writeEndOfFrame()

    def hwImpl(self) -> None:
        hls = HlsScope(self)
        dataOut = IoProxyAxi4Stream(hls, self.dataOut)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, dataOut))
        hls.compile()


class Axi4SWriteByte(Axi4SWriteByteOnce):

    @hlsBytecode
    def mainThread(self, dataOut: IoProxyAxi4Stream):
        while BIT.from_py(1):
            dataOut.writeStartOfFrame()
            dataOut.write(uint8_t.from_py(1))
            dataOut.writeEndOfFrame()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle


    m = Axi4SWriteByte()
    m.USE_STRB = True
    m.DATA_WIDTH = 16
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
