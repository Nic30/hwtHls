#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.ctypes import uint16_t


class Axi4SPacketCntr(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(512)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()

        self.pkt_cnt: HwIODataRdVld = HwIODataRdVld()._m()
        self.pkt_cnt.DATA_WIDTH = 16

    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        pkts = uint16_t.from_py(0)
        i.readStartOfFrame()
        while BIT.from_py(1):
            # PyBytecodeInPreproc is used because otherwise
            # the read object is converted to a RtlSignal because word= is a store to a word variable
            word = PyBytecodeInPreproc(i.read(self.i.data._dtype))
            if word._isLast():
                pkts += 1
            hls.write(pkts, self.pkt_cnt)

    def _impl(self):
        hls = HlsScope(self)
        i = IoProxyAxi4Stream(hls, self.i)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, i)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SPacketCntr()
    m.DATA_WIDTH = 16
    m.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
