#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.statementsRead import IN_STREAM_POS
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.types.ctypes import uint16_t


class AxiSPacketCntr(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(512)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            
        self.pkt_cnt: Handshaked = Handshaked()._m()
        self.pkt_cnt.DATA_WIDTH = 16

    def mainThread(self, hls: HlsScope):
        pkts = uint16_t.from_py(0)
        while BIT.from_py(1):
            word = PyBytecodeInPreproc(# PyBytecodeInPreproc is used because otherwise 
                                       # the read object is converted to a RtlSignal because word= is a store to a word variable
                hls.read(self.i, self.i.data._dtype,
                inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END))

            if word._isLast():
                pkts += 1
            hls.write(pkts, self.pkt_cnt)

    def _impl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        # mainThread.bytecodeToSsa.debug = True
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSPacketCntr()
    u.DATA_WIDTH = 16
    u.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
