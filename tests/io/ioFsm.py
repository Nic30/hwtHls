#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc


class WriteFsm0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: VectSignal = VectSignal(self.DATA_WIDTH, signed=False)._m()

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        hls.thread(
            hls.While(True,
                hls.write(1, self.o),
                hls.write(2, self.o),
                hls.write(3, self.o),
            )
        )
        hls.compile()



class WriteFsm0Once(WriteFsm0):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        hls.thread(
            hls.write(1, self.o),
            hls.write(2, self.o),
            hls.write(3, self.o),
        )
        hls.compile()


class WriteFsm1(WriteFsm0):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.o: HsStructIntf = HsStructIntf()._m()
        self.o.T = Bits(self.DATA_WIDTH)


class WriteFsm1Once(WriteFsm1):

    def _impl(self) -> None:
        WriteFsm0Once._impl(self)


class ReadFsm0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(8)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i = VectSignal(self.DATA_WIDTH)
        self.o = VectSignal(3 * self.DATA_WIDTH)._m()

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        r = [hls.read(self.i) for _ in range(3)]
        hls.thread(
            hls.While(True,
                *r,
                hls.write(Concat(*reversed(r)), self.o),
            )
        )
        hls.compile()



class ReadFsm0Once(ReadFsm0):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        r = [hls.read(self.i) for _ in range(3)]
        hls.thread(
            *r,
            hls.write(Concat(*reversed(r)), self.o),
        )
        hls.compile()



class ReadFsm1(ReadFsm0):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ

        self.i: HsStructIntf = HsStructIntf()
        self.i.T = Bits(self.DATA_WIDTH)       
        self.o: HsStructIntf = HsStructIntf()._m()
        self.o.T = Bits(3 * self.DATA_WIDTH)


class ReadFsm1Once(ReadFsm1):

    def _impl(self) -> None:
        ReadFsm0Once._impl(self)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = WriteFsm1Once()
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
