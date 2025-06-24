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
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc
from hwtHls.frontend.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.amba.axis_comp.frame_parser.test_types import structManyInts
from hwtLib.types.ctypes import uint16_t, uint32_t


class Axi4SParseStructManyInts0(HwModule):
    AXI_CLS = Axi4Stream

    @override
    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(64)
        self.CLK_FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        o: HObjList[HwIODataRdVld] = HObjList()
        for f in structManyInts.fields:
            if f.name is not None:
                _o = HwIODataRdVld()._m()
                _o.DATA_WIDTH = f.dtype.bit_length()
                o.append(_o)

        self.o = o

    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream) -> None:
        while b1:
            i.readStartOfFrame()
            v = i.read(structManyInts, reliable=True).data
            i.readEndOfFrame()
            for i, dst in enumerate(self.o):
                hls.write(getattr(v, f"i{i:d}"), dst)

    @override
    def hwImpl(self) -> None:
        hls = HlsScope(self, namePrefix="")
        i = IoProxyAxi4Stream(hls, self.i)
        hls.addThread(HlsThreadFromPy(hls, self.mainThread, hls, i))
        hls.compile()


class Axi4SParseStructManyInts1(Axi4SParseStructManyInts0):
    """
    :note: same as :class:`~.Axi4SParseStructManyInts1` just read field by field
    """

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream) -> None:
        while b1:
            i.readStartOfFrame()
            values = [
                # :note: actual read is performed once this read object is found in some expression
                # which happens in output write loop
                i.read(f.dtype, reliable=True)
                for f in structManyInts.fields
            ]

            oIt = iter(self.o)
            assert len(values) == len(structManyInts.fields)
            for src, f in zip(values, structManyInts.fields):
                if f.name is not None:
                    dst = PyBytecodeInPreproc(next(oIt))
                    hls.write(src.data, dst)

            i.readEndOfFrame()


struct_i16_i32 = HStruct(
    (uint16_t, "i16"),
    (uint32_t, "i32"),
)


class Axi4SParse2fields(Axi4SParseStructManyInts0):

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()

        o: HObjList[HwIODataRdVld] = HObjList(HwIODataRdVld()._m() for _ in range(2))
        o[0].DATA_WIDTH = 16
        o[1].DATA_WIDTH = 32
        self.o = o

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream) -> None:
        while b1:
            i.readStartOfFrame()
            v0 = i.read(uint16_t, reliable=True)
            v1 = i.read(uint32_t, reliable=True)
            i.readEndOfFrame()
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
