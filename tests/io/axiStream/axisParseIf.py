#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.utils import addClkRstn
from hwtHls.hlsStreamProc.statementsIo import IN_STREAM_POS
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
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
        hls = HlsStreamProc(self)
        v0 = hls.read(self.i, Bits(16), inStreamPos=IN_STREAM_POS.BEGIN)
        v1a = hls.read(self.i, Bits(16), inStreamPos=IN_STREAM_POS.END)
        v1b = hls.read(self.i, Bits(32), inStreamPos=IN_STREAM_POS.END)
        o = self.o

        hls.thread(
            hls.While(True,
                v0,
                hls.If(v0._eq(2),
                       v1a, # read 2B, output
                       hls.write(v1a._reinterpret_cast(o._dtype), o),
                ).Elif(v0._eq(4),
                       v1b, # read 4B, output
                       hls.write(v1b._reinterpret_cast(o._dtype), o),
                ).Else(
                    # read 1B only
                    hls.read(self.i, Bits(8), inStreamPos=IN_STREAM_POS.END)
                )
            )
        )


class AxiSParse2IfAndSequel(AxiSParse2fields):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o = HsStructIntf()._m()
        self.o.T = Bits(32)

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        v0 = hls.read(self.i, Bits(16), inStreamPos=IN_STREAM_POS.BEGIN)
        v1a = hls.read(self.i, Bits(24))
        v1b = hls.read(self.i, Bits(32))
        v2 = hls.read(self.i, Bits(8), inStreamPos=IN_STREAM_POS.END)
        o = self.o

        hls.thread(
            hls.While(True,
                v0,
                hls.If(v0._eq(3),
                       v1a,
                       hls.write(v1a._reinterpret_cast(o._dtype), o),
                ).Elif(v0._eq(4),
                       v1b,
                       hls.write(v1b._reinterpret_cast(o._dtype), o),
                ),
                v2,
                hls.write(v2._reinterpret_cast(o._dtype), o),
            )
        )


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform, makeDebugPasses
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParse2If()
    u.DATA_WIDTH = 8
    u.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(**makeDebugPasses("tmp"))
    print(to_rtl_str(u, target_platform=p))
