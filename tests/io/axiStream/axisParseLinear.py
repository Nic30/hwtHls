#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.statementsIo import IN_STREAM_POS
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.amba.axis import AxiStream
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.types.ctypes import uint16_t, uint32_t


class AxiSParseStructManyInts0(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(64)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
        o: HObjList[Handshaked] = HObjList()
        for f in structManyInts.fields:
            if f.name is not None:
                _o = Handshaked()._m()
                _o.DATA_WIDTH = f.dtype.bit_length()
                o.append(_o)

        self.o = o

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        v = hls.read(self.i, structManyInts, inStreamPos=IN_STREAM_POS.BEGIN_END)

        hls.thread(
            hls.While(True,
                v,
                *(
                    hls.write(getattr(v.data, f"i{i:d}"), dst)
                    for i, dst in enumerate(self.o)
                )
            )
        )
        hls.compile()



class AxiSParseStructManyInts1(AxiSParseStructManyInts0):
    """
    :note: same as :class:`~.AxiSParseStructManyInts1` just read field by field
    """

    def _impl(self) -> None:
        hls = HlsStreamProc(self)
        v = [
            hls.read(self.i, f.dtype, inStreamPos=
                     IN_STREAM_POS.BEGIN_END if i == 0 and last else 
                     IN_STREAM_POS.BEGIN if i == 0 else
                     IN_STREAM_POS.END if last else
                     IN_STREAM_POS.BODY)
            for last, (i, f) in iter_with_last(enumerate(structManyInts.fields))
        ]

        def write():
            oIt = iter(self.o)
            assert len(v) == len(structManyInts.fields)
            for src, f in zip(v, structManyInts.fields):
                if f.name is not None:
                    dst = next(oIt)
                    yield hls.write(src.data, dst)

        hls.thread(
            hls.While(True,
               *v,
                *write(),
            )
        )
        hls.compile()



struct_i16_i32 = HStruct(
    (uint16_t, "i16"),
    (uint32_t, "i32"),
)


class AxiSParse2fields(AxiSParseStructManyInts0):
    
    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()

        o: HObjList[Handshaked] = HObjList(Handshaked()._m() for _ in range(2))
        o[0].DATA_WIDTH = 16
        o[1].DATA_WIDTH = 32
        self.o = o

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
                    hls.write(src.data, dst)
                    for src, dst in zip(v, self.o)
                )
            )
        )
        hls.compile()



if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform, makeDebugPasses
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParseStructManyInts1()
    u.DATA_WIDTH = 512
    p = VirtualHlsPlatform(**makeDebugPasses("tmp"))
    print(to_rtl_str(u, target_platform=p))
