#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from tests.io.amba.axiStream.axisParseLinear import AxiSParse2fields
from hwt.synthesizer.param import Param
from hwtLib.amba.axis_comp.builder import AxiSBuilder


class AxiSParse2If2B(AxiSParse2fields):
    """
    Optionally read second byte from input stream
    """

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(8)

    def _impl(self) -> None:
        hls = HlsScope(self)
        # add register to prevent zero time data exchange ins sim (to see nicely transaction nicely in wave)
        i = self.i
        o = self.o
        v0 = HlsStmReadAxiStream(hls, i, Bits(8), True)
        v1 = HlsStmReadAxiStream(hls, i, Bits(8), True)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, i),
                v0,
                ast.If(v0.data._eq(2),
                    v1,  # read 2B, output
                    hls.write(v1.data, o),
                ).Else(
                    hls.write(v0.data._reinterpret_cast(o._dtype), o),
                ),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()


class AxiSParse2IfLess(AxiSParse2fields):
    """
    Read packet in following fomat: 1B header, 2 or 0B footer
    """

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsScope(self)
        # add register to prevent zero time data exchange ins sim (to see nicely transaction nicely in wave)
        i = self.i
        o = self.o
        v0 = HlsStmReadAxiStream(hls, i, Bits(8), True)
        v1a = HlsStmReadAxiStream(hls, i, Bits(16), True)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, i),
                v0,
                ast.If(v0.data < 128,
                    v1a,  # read 2B, output
                    hls.write(v1a.data._reinterpret_cast(o._dtype), o),
                ),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()


class AxiSParse2If(AxiSParse2fields):
    """
    Read packet in following fomat: 2B header, 2 or 4 or 1B footer
    """

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsScope(self)
        # add register to prevent zero time data exchange ins sim (to see nicely transaction nicely in wave)
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
                    v1a,  # read 2B, output
                    hls.write(v1a.data._reinterpret_cast(o._dtype), o),
                ).Elif(v0.data._eq(4),
                    v1b,  # read 4B, output
                    hls.write(v1b.data._reinterpret_cast(o._dtype), o),
                ).Else(
                    # read 1B only
                    HlsStmReadAxiStream(hls, i, Bits(8), True)
                ),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()


class AxiSParse2IfAndSequel(AxiSParse2fields):
    """
    Read packet in following format: 2B header, 3 or 4 or 0 bytes, 1B footer 
    """
    def _config(self)->None:
        AxiSParse2fields._config(self)
        self.WRITE_FOOTER = Param(True)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsScope(self)
        i = AxiSBuilder(self, self.i).buff(1).end
        o = self.o
        v0 = HlsStmReadAxiStream(hls, i, Bits(16), True)
        v1a = HlsStmReadAxiStream(hls, i, Bits(24), True)
        v1b = HlsStmReadAxiStream(hls, i, Bits(32), True)
        v2 = HlsStmReadAxiStream(hls, i, Bits(8), True)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, i),
                v0,
                ast.If(v0.data._eq(3),
                       v1a,
                       hls.write(v1a.data._reinterpret_cast(o._dtype), o),
                ).Elif(v0.data._eq(4),
                       v1b,
                       hls.write(v1b.data._reinterpret_cast(o._dtype), o),
                ),
                v2,
                *([hls.write(v2.data._reinterpret_cast(o._dtype), o)] if self.WRITE_FOOTER else ()),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = AxiSParse2IfAndSequel()
    u.DATA_WIDTH = 16
    u.CLK_FREQ = int(40e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    p._debugExpandCompositeNodes = True
    print(to_rtl_str(u, target_platform=p))
