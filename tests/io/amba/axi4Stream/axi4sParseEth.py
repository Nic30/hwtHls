#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.net.ethernet import Eth2Header_t, eth_mac_t
from tests.frontend.ast.trivial import WriteOnce


class Axi4SParseEth(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(512)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
            self.dst_mac: HwIOStructRdVld[eth_mac_t] = HwIOStructRdVld()._m()
            self.dst_mac.T = eth_mac_t

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            HlsStmReadStartOfFrame(hls, self.i),
            eth = HlsStmReadAxi4Stream(hls, self.i, Eth2Header_t, True)
            HlsStmReadEndOfFrame(hls, self.i),
            hls.write(eth.data.dst, self.dst_mac)
    
    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SParseEth()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
