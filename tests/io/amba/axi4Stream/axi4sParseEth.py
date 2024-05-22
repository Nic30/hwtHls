#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.net.ethernet import Eth2Header_t, eth_mac_t
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame


class Axi4SParseEth(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(512)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
            self.dst_mac: HwIOStructRdVld[eth_mac_t] = HwIOStructRdVld()._m()
            self.dst_mac.T = eth_mac_t

    def _impl(self) -> None:
        hls = HlsScope(self)

        # :note: the read has to be put somewhere in the code later
        # because it needs to have a code location where it happens
        # we declare it as python variable so we do not need to use tmp
        # variable in hls
        eth = HlsStmReadAxi4Stream(hls, self.i, Eth2Header_t, True)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, self.i),
                eth,
                HlsStmReadEndOfFrame(hls, self.i),
                hls.write(eth.data.dst, self.dst_mac)
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SParseEth()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
