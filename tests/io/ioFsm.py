#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.std import HwIOVectSignal
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.scope import HlsScope
from tests.frontend.ast.trivial import WriteOnce


class WriteFsm0WhileTrue123(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: HwIOVectSignal = HwIOVectSignal(self.DATA_WIDTH, signed=False)._m()

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write(1, self.o)
            hls.write(2, self.o)
            hls.write(3, self.o)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class WriteFsm0Send123(WriteFsm0WhileTrue123):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        hls.write(1, self.o)
        hls.write(2, self.o)
        hls.write(3, self.o)


class WriteFsm1WhileTrue123hs(WriteFsm0WhileTrue123):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.o.T = HBits(self.DATA_WIDTH)


class WriteFsm1Send123hs(WriteFsm0Send123):

    @override
    def hwDeclr(self):
        WriteFsm1WhileTrue123hs.hwDeclr(self)


class ReadFsm0WhileTrueRead3TimesWriteConcat(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i = HwIOVectSignal(self.DATA_WIDTH)
        self.o = HwIOVectSignal(3 * self.DATA_WIDTH)._m()

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            r = [hls.read(self.i) for _ in range(3)]
            hls.write(Concat(*reversed([_r.data for _r in r])), self.o),

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class ReadFsm0Read3TimesWriteConcat(ReadFsm0WhileTrueRead3TimesWriteConcat):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        r = [hls.read(self.i) for _ in range(3)]
        hls.write(Concat(*reversed([_r.data for _r in r])), self.o),


class ReadFsm1WhileTrueRead3TimesWriteConcatHs(ReadFsm0WhileTrueRead3TimesWriteConcat):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i: HwIOStructRdVld = HwIOStructRdVld()
        self.i.T = HBits(self.DATA_WIDTH)
        self.o: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.o.T = HBits(3 * self.DATA_WIDTH)


class ReadFsm1Read3TimesWriteConcatHs(ReadFsm0Read3TimesWriteConcat):

    @override
    def hwDeclr(self):
        ReadFsm1WhileTrueRead3TimesWriteConcatHs.hwDeclr(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = WriteFsm1WhileTrue123hs()
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
