#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope


class WriteOnce(HwModule):

    @override
    def hwConfig(self):
        self.FREQ = HwParam(int(100e6))
        self.DATA_WIDTH = HwParam(8)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        o = self.dataOut = HwIOStructRdVld()._m()
        o.T = HBits(self.DATA_WIDTH, signed=False)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        hls.write(1, self.dataOut)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls))
        hls.compile()


class ReadWriteOnce0(WriteOnce):

    @override
    def hwDeclr(self):
        super(ReadWriteOnce0, self).hwDeclr()
        i = self.dataIn = HwIOStructRdVld()
        i.T = HBits(self.DATA_WIDTH, signed=False)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        hls.write(hls.read(self.dataIn).data, self.dataOut)


class ReadWriteOnce1(ReadWriteOnce0):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        tmp = hls.read(self.dataIn).data
        hls.write(tmp, self.dataOut)


class ReadWriteOnce2(ReadWriteOnce0):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        tmp = hls.read(self.dataIn).data
        hls.write(tmp + 1, self.dataOut)


class WhileTrueWrite(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self) -> None:
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        self.dataOut: HwIOStructRdVld = HwIOStructRdVld()._m()
        self.dataOut.T = HBits(self.DATA_WIDTH, signed=False)

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write(10, self.dataOut)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class WhileTrueReadWrite(WhileTrueWrite):

    @override
    def hwDeclr(self) -> None:
        super(WhileTrueReadWrite, self).hwDeclr()
        i = self.dataIn = HwIOStructRdVld()
        i.T = HBits(self.DATA_WIDTH, signed=False)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write(hls.read(self.dataIn).data, self.dataOut)


class WhileTrueReadWriteExpr(WhileTrueReadWrite):

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        while b1:
            hls.write((hls.read(self.dataIn).data * 8 + 2) * 3, self.dataOut)


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle
    m = WhileTrueReadWriteExpr()
    m.FREQ = int(150e6)
    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
