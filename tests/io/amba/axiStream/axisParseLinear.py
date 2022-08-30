#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.struct import HStruct
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.hObjList import HObjList
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.types.ctypes import uint16_t, uint32_t
from hwtHls.io.amba.axiStream.stmRead import HlsStmReadAxiStream
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame


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
        hls = HlsScope(self)
        v = HlsStmReadAxiStream(hls, self.i, structManyInts, True)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, self.i),
                v,
                HlsStmReadEndOfFrame(hls, self.i),
                *(
                    hls.write(getattr(v.data, f"i{i:d}"), dst)
                    for i, dst in enumerate(self.o)
                )
            ),
            self._name)
        )
        hls.compile()


class AxiSParseStructManyInts1(AxiSParseStructManyInts0):
    """
    :note: same as :class:`~.AxiSParseStructManyInts1` just read field by field
    """

    def _impl(self) -> None:
        hls = HlsScope(self)
        v = [
            HlsStmReadAxiStream(hls, self.i, f.dtype, True)
            for f in structManyInts.fields
        ]

        def write():
            oIt = iter(self.o)
            assert len(v) == len(structManyInts.fields)
            for src, f in zip(v, structManyInts.fields):
                if f.name is not None:
                    dst = next(oIt)
                    yield hls.write(src.data, dst)

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, self.i),
                *v,
                HlsStmReadEndOfFrame(hls, self.i),
                *write(),
            ),
            self._name)
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
        hls = HlsScope(self)
        v = [
            HlsStmReadAxiStream(hls, self.i, uint16_t, True),
            HlsStmReadAxiStream(hls, self.i, uint32_t, True),
        ]

        ast = HlsAstBuilder(hls)
        hls.addThread(HlsThreadFromAst(hls,
            ast.While(True,
                HlsStmReadStartOfFrame(hls, self.i),
                *v,
                HlsStmReadEndOfFrame(hls, self.i),
                *(
                    hls.write(src.data, dst)
                    for src, dst in zip(v, self.o)
                )
            ),
            self._name)
        )
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSParseStructManyInts1()
    u.DATA_WIDTH = 512
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
