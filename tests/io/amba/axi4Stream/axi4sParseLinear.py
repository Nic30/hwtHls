#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hObjList import HObjList
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.struct import HStruct
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.ast.statementsRead import HlsStmReadStartOfFrame, \
    HlsStmReadEndOfFrame
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInPreproc
from hwtHls.io.amba.axi4Stream.stmRead import HlsStmReadAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.types.ctypes import uint16_t, uint32_t
from tests.frontend.ast.trivial import WriteOnce


class Axi4SParseStructManyInts0(HwModule):

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(64)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = Axi4Stream()
        o: HObjList[HwIODataRdVld] = HObjList()
        for f in structManyInts.fields:
            if f.name is not None:
                _o = HwIODataRdVld()._m()
                _o.DATA_WIDTH = f.dtype.bit_length()
                o.append(_o)

        self.o = o

    @hlsBytecode
    def mainThread(self, hls: HlsScope) -> None:
        while b1:
            HlsStmReadStartOfFrame(hls, self.i)
            v = HlsStmReadAxi4Stream(hls, self.i, structManyInts, True).data
            HlsStmReadEndOfFrame(hls, self.i)
            for i, dst in enumerate(self.o):
                hls.write(getattr(v, f"i{i:d}"), dst)

    @override
    def hwImpl(self) -> None:
        WriteOnce.hwImpl(self)


class Axi4SParseStructManyInts1(Axi4SParseStructManyInts0):
    """
    :note: same as :class:`~.Axi4SParseStructManyInts1` just read field by field
    """

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope) -> None:
        i = PyBytecodeInPreproc(self.i)
        while b1:
            HlsStmReadStartOfFrame(hls, i)
            values = [
                # :note: actual read is performed once this read object is found in some expression
                # which happens in output write loop
                HlsStmReadAxi4Stream(hls, i, f.dtype, True)
                for f in structManyInts.fields
            ]

            oIt = iter(self.o)
            assert len(values) == len(structManyInts.fields)
            for src, f in zip(values, structManyInts.fields):
                if f.name is not None:
                    dst = PyBytecodeInPreproc(next(oIt))
                    hls.write(src.data, dst)

            HlsStmReadEndOfFrame(hls, i)

struct_i16_i32 = HStruct(
    (uint16_t, "i16"),
    (uint32_t, "i32"),
)


class Axi4SParse2fields(Axi4SParseStructManyInts0):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = Axi4Stream()

        o: HObjList[HwIODataRdVld] = HObjList(HwIODataRdVld()._m() for _ in range(2))
        o[0].DATA_WIDTH = 16
        o[1].DATA_WIDTH = 32
        self.o = o

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope) -> None:
        i = PyBytecodeInPreproc(self.i)
        while b1:
            HlsStmReadStartOfFrame(hls, i)
            v0 = HlsStmReadAxi4Stream(hls, i, uint16_t, True)
            v1 = HlsStmReadAxi4Stream(hls, i, uint32_t, True)
            HlsStmReadEndOfFrame(hls, i)
            for src, dst in zip([v0, v1], self.o):
                hls.write(src.data, dst)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = Axi4SParse2fields()
    m.DATA_WIDTH = 48
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
