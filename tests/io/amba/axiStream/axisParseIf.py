#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.amba.axis_comp.builder import AxiSBuilder
from tests.io.amba.axiStream.axisParseLinear import AxiSParse2fields
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from tests.frontend.pyBytecode.stmWhile import TRUE
from hwtHls.io.amba.axiStream.proxy import IoProxyAxiStream
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy


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
    Read packet in following format: 1B header, 2 or 0B footer
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
    Read packet in following format: 2B header, 2 or 4 or 1B footer
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

    def _config(self) -> None:
        AxiSParse2fields._config(self)
        self.WRITE_FOOTER = Param(True)
        self.USE_PY_FRONTEND = Param(False)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsScope(self)
        if self.USE_PY_FRONTEND:
            i = IoProxyAxiStream(hls, self.i)
            t = HlsThreadFromPy(hls, self._implPy, hls, i)
        else:
            ast = HlsAstBuilder(hls)
            t = HlsThreadFromAst(hls, self._implAst(hls, ast), self._name)
        hls.addThread(t)
        hls.compile()

    def _implAst(self, hls: HlsScope, ast: HlsAstBuilder) -> None:
        i = self.i
        o = self.o
        v0 = HlsStmReadAxiStream(hls, i, Bits(16), True)
        v1a = HlsStmReadAxiStream(hls, i, Bits(24), True)
        v1b = HlsStmReadAxiStream(hls, i, Bits(32), True)
        v2 = HlsStmReadAxiStream(hls, i, Bits(8), True)

        return\
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
        )

    def _implPy(self, hls: HlsScope, i: IoProxyAxiStream):
        o = PyBytecodeInPreproc(self.o)

        while TRUE:
            i.readStartOfFrame()
            v0 = PyBytecodeInPreproc(i.read(Bits(16)))
            if v0.data._eq(3):
                v1a = PyBytecodeInPreproc(i.read(Bits(24)))
                hls.write(v1a.data._reinterpret_cast(o._data), o)

            elif v0.data._eq(4):
                v1b = PyBytecodeInPreproc(i.read(Bits(32)))
                hls.write(v1b.data._reinterpret_cast(o._dtype), o),

            v2 = PyBytecodeInPreproc(i.read(Bits(8)))
            if self.WRITE_FOOTER:
                hls.write(v2.data._reinterpret_cast(o._dtype), o)

            i.readEndOfFrame()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = AxiSParse2IfAndSequel()
    u.DATA_WIDTH = 48
    u.CLK_FREQ = int(1e6)
    u.USE_PY_FRONTEND = False
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    p._debugExpandCompositeNodes = True
    print(to_rtl_str(u, target_platform=p))
