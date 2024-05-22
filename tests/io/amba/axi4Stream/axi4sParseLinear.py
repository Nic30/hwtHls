#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hObjList import HObjList
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.ast.builder import HlsAstBuilder
from hwtHls.frontend.ast.thread import HlsThreadFromAst
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.types.ctypes import uint16_t, uint32_t
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame


class Axi4SParseStructManyInts0(HwModule):

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(64)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
        o: HObjList[HwIODataRdVld] = HObjList()
        for f in structManyInts.fields:
            if f.name is not None:
                _o = HwIODataRdVld()._m()
                _o.DATA_WIDTH = f.dtype.bit_length()
                o.append(_o)

        self.o = o

    def _impl(self) -> None:
        hls = HlsScope(self)
        v = HlsStmReadAxi4Stream(hls, self.i, structManyInts, True)

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


class Axi4SParseStructManyInts1(Axi4SParseStructManyInts0):
    """
    :note: same as :class:`~.Axi4SParseStructManyInts1` just read field by field
    """

    def _impl(self) -> None:
        hls = HlsScope(self)
        v = [
            HlsStmReadAxi4Stream(hls, self.i, f.dtype, True)
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


class Axi4SParse2fields(Axi4SParseStructManyInts0):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()

        o: HObjList[HwIODataRdVld] = HObjList(HwIODataRdVld()._m() for _ in range(2))
        o[0].DATA_WIDTH = 16
        o[1].DATA_WIDTH = 32
        self.o = o

    def _impl(self) -> None:
        hls = HlsScope(self)
        v = [
            HlsStmReadAxi4Stream(hls, self.i, uint16_t, True),
            HlsStmReadAxi4Stream(hls, self.i, uint32_t, True),
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
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SParseStructManyInts0()
    m.DATA_WIDTH = 16
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
