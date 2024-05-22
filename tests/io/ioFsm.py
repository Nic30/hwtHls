#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope


class WriteFsm0WhileTrue123(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: HwIOVectSignal = HwIOVectSignal(self.DATA_WIDTH, signed=False)._m()

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

        self.o: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.o.T = HBits(self.DATA_WIDTH)


class WriteFsm1Send123hs(WriteFsm1WhileTrue123hs):

    def _impl(self) -> None:
        WriteFsm0Send123._impl(self)


class ReadFsm0WhileTrueRead3TimesWriteConcat(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i = HwIOVectSignal(self.DATA_WIDTH)
        self.o = HwIOVectSignal(3 * self.DATA_WIDTH)._m()

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

        self.i: HwIOStructRdVld = HwIOStructRdVld()
        self.i.T = HBits(self.DATA_WIDTH)
        self.o: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.o.T = HBits(3 * self.DATA_WIDTH)


class ReadFsm1Read3TimesWriteConcatHs(ReadFsm1WhileTrueRead3TimesWriteConcatHs):

    def _impl(self) -> None:
        ReadFsm0Read3TimesWriteConcat._impl(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = WriteFsm1WhileTrue123hs()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
