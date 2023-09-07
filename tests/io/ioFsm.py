#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope


class WriteFsm0WhileTrue123(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: VectSignal = VectSignal(self.DATA_WIDTH, signed=False)._m()

    def _impl(self) -> None:
        hls = HlsScope(self)
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            ),
            self._name)

        )
        hls.compile()



class WriteFsm0Send123(WriteFsm0WhileTrue123):

    def _impl(self) -> None:
        hls = HlsScope(self)
        hls.addThread(
            HlsThreadFromAst(hls, [
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            ],
            self._name)
        )
        hls.compile()


class WriteFsm1WhileTrue123hs(WriteFsm0WhileTrue123):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: HsStructIntf = HsStructIntf()._m()
        self.o.T = Bits(self.DATA_WIDTH)


class WriteFsm1Send123hs(WriteFsm1WhileTrue123hs):

    def _impl(self) -> None:
        WriteFsm0Send123._impl(self)


class ReadFsm0WhileTrueRead3TimesWriteConcat(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i = VectSignal(self.DATA_WIDTH)
        self.o = VectSignal(3 * self.DATA_WIDTH)._m()

    def _impl(self) -> None:
        hls = HlsScope(self)
        r = [hls.read(self.i) for _ in range(3)]
        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                *r,
                hls.write(Concat(*reversed([_r.data for _r in r])), self.o),
            ),
            self._name)
        )
        hls.compile()



class ReadFsm0Read3TimesWriteConcat(ReadFsm0WhileTrueRead3TimesWriteConcat):

    def _impl(self) -> None:
        hls = HlsScope(self)
        r = [hls.read(self.i) for _ in range(3)]
        hls.addThread(HlsThreadFromAst(hls, [
                *r,
                hls.write(Concat(*reversed([_r.data for _r in r])), self.o),
            ],
            self._name)
        )
        hls.compile()



class ReadFsm1WhileTrueRead3TimesWriteConcatHs(ReadFsm0WhileTrueRead3TimesWriteConcat):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i: HsStructIntf = HsStructIntf()
        self.i.T = Bits(self.DATA_WIDTH)
        self.o: HsStructIntf = HsStructIntf()._m()
        self.o.T = Bits(3 * self.DATA_WIDTH)


class ReadFsm1Read3TimesWriteConcatHs(ReadFsm1WhileTrueRead3TimesWriteConcatHs):

    def _impl(self) -> None:
        ReadFsm0Read3TimesWriteConcat._impl(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    u = WriteFsm1WhileTrue123hs()
    print(to_rtl_str(u, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
