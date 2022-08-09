#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.io.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from tests.io.axiStream.axisParseLinear import AxiSParse2fields


class AxiSParse2If(AxiSParse2fields):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = self.i
        o = self.o
        v0 = HlsStmReadAxiStream(hls, i, Bits(16), True)
        v1a = HlsStmReadAxiStream(hls, i, Bits(16), True)
        v1b = HlsStmReadAxiStream(hls, i, Bits(32), True)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, i),
                v0,
                ast.If(v0.data._eq(2),
                    v1a, # read 2B, output
                    hls.write(v1a.data._reinterpret_cast(o._dtype), o),
                ).Elif(v0.data._eq(4),
                    v1b, # read 4B, output
                    hls.write(v1b.data._reinterpret_cast(o._dtype), o),
                ).Else(
                    # read 1B only
                    HlsStmReadAxiStream(hls, self.i, Bits(8), True)
                ),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()


class AxiSParse2IfAndSequel(AxiSParse2fields):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = self.i
        o = self.o
        v0 =  HlsStmReadAxiStream(hls, i, Bits(16), True)
        v1a = HlsStmReadAxiStream(hls, i, Bits(24), True)
        v1b = HlsStmReadAxiStream(hls, i, Bits(32), True)
        v2 =  HlsStmReadAxiStream(hls, i, Bits(8), True)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, i),
                v0,
                ast.If(v0._eq(3),
                       v1a,
                       hls.write(v1a._reinterpret_cast(o._dtype), o),
                ).Elif(v0._eq(4),
                       v1b,
                       hls.write(v1b._reinterpret_cast(o._dtype), o),
                ),
                v2,
                hls.write(v2._reinterpret_cast(o._dtype), o),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()



if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParse2If()
    u.DATA_WIDTH = 512
    u.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
