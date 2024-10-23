#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from tests.frontend.pyBytecode.stmWhile import TRUE
from tests.io.amba.axi4Stream.axi4sParseLinear import Axi4SParse2fields


class Axi4SParse2If2B(Axi4SParse2fields):
    """
    Optionally read second byte from input stream
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(8)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        # add register to prevent zero time data exchange ins sim (to see nicely transaction nicely in wave)
        i = self.i
        o = self.o
        v0 = HlsStmReadAxi4Stream(hls, i, HBits(8), True)
        v1 = HlsStmReadAxi4Stream(hls, i, HBits(8), True)

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


class Axi4SParse2IfLess(Axi4SParse2fields):
    """
    Read packet in following format: 1B header, 2 or 0B footer
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(32)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        # add register to prevent zero time data exchange ins sim (to see nicely transaction nicely in wave)
        i = self.i
        o = self.o
        v0 = HlsStmReadAxi4Stream(hls, i, HBits(8), True)
        v1a = HlsStmReadAxi4Stream(hls, i, HBits(16), True)

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


class Axi4SParse2If(Axi4SParse2fields):
    """
    Read packet in following format: 2B header, 2 or 4 or 1B footer
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(32)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        # add register to prevent zero time data exchange ins sim (to see nicely transaction nicely in wave)
        i = self.i
        o = self.o
        v0 = HlsStmReadAxi4Stream(hls, i, HBits(16), True)
        v1a = HlsStmReadAxi4Stream(hls, i, HBits(16), True)
        v1b = HlsStmReadAxi4Stream(hls, i, HBits(32), True)

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
                    HlsStmReadAxi4Stream(hls, i, HBits(8), True)
                ),
                HlsStmReadEndOfFrame(hls, i),
            ),
            self._name)
        )
        hls.compile()


class Axi4SParse2IfAndSequel(Axi4SParse2fields):
    """
    Read packet in following format: 2B header, 3 or 4 or 0 bytes, 1B footer 
    """

    @override
    def hwConfig(self) -> None:
        Axi4SParse2fields.hwConfig(self)
        self.WRITE_FOOTER = HwParam(True)
        self.USE_PY_FRONTEND = HwParam(False)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(32)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self)
        if self.USE_PY_FRONTEND:
            i = IoProxyAxi4Stream(hls, self.i)
            t = HlsThreadFromPy(hls, self._implPy, hls, i)
        else:
            ast = HlsAstBuilder(hls)
            t = HlsThreadFromAst(hls, self._implAst(hls, ast), self._name)
        hls.addThread(t)
        hls.compile()

    def _implAst(self, hls: HlsScope, ast: HlsAstBuilder) -> None:
        i = self.i
        o = self.o
        v0 = HlsStmReadAxi4Stream(hls, i, HBits(16), True)
        v1a = HlsStmReadAxi4Stream(hls, i, HBits(24), True)
        v1b = HlsStmReadAxi4Stream(hls, i, HBits(32), True)
        v2 = HlsStmReadAxi4Stream(hls, i, HBits(8), True)

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

    def _implPy(self, hls: HlsScope, i: IoProxyAxi4Stream):
        o = PyBytecodeInPreproc(self.o)

        while TRUE:
            i.readStartOfFrame()
            v0 = PyBytecodeInPreproc(i.read(HBits(16)))
            if v0.data._eq(3):
                v1a = PyBytecodeInPreproc(i.read(HBits(24)))
                hls.write(v1a.data._reinterpret_cast(o._data), o)

            elif v0.data._eq(4):
                v1b = PyBytecodeInPreproc(i.read(HBits(32)))
                hls.write(v1b.data._reinterpret_cast(o._dtype), o),

            v2 = PyBytecodeInPreproc(i.read(HBits(8)))
            if self.WRITE_FOOTER:
                hls.write(v2.data._reinterpret_cast(o._dtype), o)

            i.readEndOfFrame()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SParse2IfAndSequel()
    m.DATA_WIDTH = 48
    m.CLK_FREQ = int(1e6)
    m.USE_PY_FRONTEND = False
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    p._debugExpandCompositeNodes = True
    print(to_rtl_str(m, target_platform=p))
