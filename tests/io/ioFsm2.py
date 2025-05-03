#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.scope import HlsScope
from hwtLib.types.ctypes import uint8_t
from tests.frontend.ast.whileTrue import WhileTrueWriteCntr0
from tests.io.ioFsm import WriteFsm1WhileTrue123hs
from hwtHls.frontend.pyBytecode.hwrange import hwrange
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwt.hdl.commonConstants import b1
from hwtHls.code import zext


class WriteFsmFor(WriteFsm1WhileTrue123hs):
    """
    IO write FSM inside of pipeline
    """

    @override
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        for _ in hwrange(3):
            hls.write(1, self.o)
            hls.write(2, self.o)
            hls.write(3, self.o)


class WriteFsmPrequel(WriteFsm1WhileTrue123hs):
    """
    IO write FSM before pipeline
    """

    @override
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        hls.write(99, self.o),
        hls.write(100, self.o),
        for _i in hwrange(3):
            i = zext(_i, self.DATA_WIDTH)
            hls.write(i + 1, self.o)
            hls.write(i + 2, self.o)
            hls.write(i + 3, self.o)


class WriteFsmIf(WriteFsm1WhileTrue123hs):

    @override
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        i = uint8_t.from_py(0)
        while b1:
            if i._eq(0):
                hls.write(1, self.o)
                hls.write(2, self.o)
                i = 1
            else:
                hls.write(3, self.o)
                i = 0


class WriteFsmIfOptionalInMiddle(WriteFsm1WhileTrue123hs):

    @override
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        i = uint8_t.from_py(0)
        while b1:
            hls.write(1, self.o)
            if i._eq(0):
                hls.write(2, self.o)
                i = 1
            else:
                i = 0
            hls.write(3, self.o)


class WriteFsmControlledFromIn(WriteFsm1WhileTrue123hs):

    @override
    def hwDeclr(self):
        WriteFsm1WhileTrue123hs.hwDeclr(self)
        self.i = HwIOStructRdVld()
        self.i.T = self.o.T

    @override
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        while b1:
            hls.write(1, self.o)
            r = hls.read(self.i)
            if r.data._eq(1):
                hls.write(2, self.o)
            else:
                hls.write(4, self.o)
                hls.write(5, self.o)
            hls.write(3, self.o)


class ReadFsmWriteFsmSumAndCondWrite(WriteFsm1WhileTrue123hs):


    @override
    def hwDeclr(self):
        WriteFsm1WhileTrue123hs.hwDeclr(self)
        self.i = HwIOStructRdVld()
        self.i.T = self.o.T

    @override
    @hlsBytecode
    def mainThread(self, hls:HlsScope):
        while b1:
            v0 = hls.read(self.i).data
            if v0._eq(0):
                continue
            v1 = hls.read(self.i).data
            if v1._eq(1):
                hls.write(1, self.o)
                hls.write(2, self.o)
                hls.write(3, self.o)

            hls.read(self.i)
            hls.write(4, self.o)
            hls.write(5, self.o)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    dut = ReadFsmWriteFsmSumAndCondWrite()
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(dut, target_platform=p))
