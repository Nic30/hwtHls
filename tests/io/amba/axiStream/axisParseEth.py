#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.types.net.ethernet import Eth2Header_t, eth_mac_t
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame


class AxiSParseEth(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(512)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            self.dst_mac: HsStructIntf[eth_mac_t] = HsStructIntf()._m()
            self.dst_mac.T = eth_mac_t

    def _impl(self) -> None:
        hls = HlsScope(self)

        # :note: the read has to be put somewhere in the code later
        # because it needs to have a code location where it happens
        # we declare it as python variable so we do not need to use tmp
        # variable in hls
        eth = HlsStmReadAxiStream(hls, self.i, Eth2Header_t, True)
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
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParseEth()
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))