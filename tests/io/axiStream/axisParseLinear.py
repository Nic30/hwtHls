#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.interfaces.std import Signal
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.amba.axis import AxiStream
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.types.ctypes import uint16_t, uint32_t
from hwtHls.hlsStreamProc.statements import IN_STREAM_POS


class AxiSParseStructManyInts0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(64)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o: HObjList[Signal] = HObjList(
            Signal(f.dtype)._m()
            for f in structManyInts.fields
            if f.name is not None
        )

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        v = hls.read(self.i, structManyInts)

        hls.thread(
            hls.While(True,
                v,
                *(
                    hls.write(getattr(v, f"i{i:d}"), dst)
                    for i, dst in enumerate(self.o)
                )
            )
        )


class AxiSParseStructManyInts1(AxiSParseStructManyInts0):

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        v = [
            hls.read(self.i, f.dtype, inStreamPos=IN_STREAM_POS.BEGIN if i == 0 else
                                                  IN_STREAM_POS.END if last else
                                                  IN_STREAM_POS.BODY)
            for last, (i, f) in iter_with_last(enumerate(structManyInts.fields))
        ]

        hls.thread(
            hls.While(True,
               *v,
                *(
                    hls.write(src, dst)
                    for src, dst in zip(v, self.o)
                )
            )
        )


class AxiSParse2fields(AxiSParseStructManyInts0):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        self.o: HObjList[Signal] = HObjList([
            Signal(uint16_t)._m(),
            Signal(uint32_t)._m(),
        ])

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        v = [
            hls.read(self.i, uint16_t, inStreamPos=IN_STREAM_POS.BEGIN),
            hls.read(self.i, uint32_t, inStreamPos=IN_STREAM_POS.END),
        ]

        hls.thread(
            hls.While(True,
               *v,
                *(
                    hls.write(src, dst)
                    for src, dst in zip(v, self.o)
                )
            )
        )


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform, makeDebugPasses
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParse2fields()
    p = VirtualHlsPlatform(**makeDebugPasses("tmp"))
    print(to_rtl_str(u, target_platform=p))
