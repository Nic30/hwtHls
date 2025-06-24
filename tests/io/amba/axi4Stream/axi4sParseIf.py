#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOStruct import HwIOStructRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaPreproc import PyBytecodeInPreproc,\
    PyBytecodeBlockLabel
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from tests.io.amba.axi4Stream.axi4sParseLinear import Axi4SParse2fields


class Axi4SParse2If2B(Axi4SParse2fields):
    """
    Optionally read second byte from input stream
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(8)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        o = PyBytecodeInPreproc(self.o)
        while b1:
            i.readStartOfFrame()
            v0 = i.read(HBits(8), reliable=True)
            if  v0.data._eq(2):
                # read 2B, output
                v1 = i.read(HBits(8), reliable=True)
                hls.write(v1.data, o)
            else:
                hls.write(v0.data._reinterpret_cast(o._dtype), o)

            i.readEndOfFrame()


class Axi4SParse2IfLess(Axi4SParse2fields):
    """
    Read packet in following format: 1B header, 2 or 0B footer
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(32)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        o = PyBytecodeInPreproc(self.o)
        while b1:
            i.readStartOfFrame()
            v0 = i.read(HBits(8), reliable=True)
            if v0.data < 128:
                # read 2B, output
                v1a = i.read(HBits(16), True)
                hls.write(v1a.data._reinterpret_cast(o.T), o)
            i.readEndOfFrame()


class Axi4SParse2If(Axi4SParse2fields):
    """
    Read packet in following format: 2B header, 2 or 4 or 1B footer
    """

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(32)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        o = PyBytecodeInPreproc(self.o)
        while b1:
            i.readStartOfFrame()
            v0 = i.read(HBits(16), reliable=True)
            if v0.data._eq(2):
                # read 2B, output
                v1a = i.read(HBits(16), reliable=True)
                hls.write(v1a.data._reinterpret_cast(o.T), o)
            elif v0.data._eq(4):
                # read 4B, output
                v1b = i.read(HBits(32), reliable=True)
                hls.write(v1b.data._reinterpret_cast(o.T), o)
            else:
                # read 1B only
                i.read(HBits(8), reliable=True)
            i.readEndOfFrame()


class Axi4SParse2IfAndSequel(Axi4SParse2fields):
    """
    Read packet in following format: 2B header, 3 or 4 or 0 bytes, 1B footer 
    """

    @override
    def hwConfig(self) -> None:
        Axi4SParse2fields.hwConfig(self)
        self.WRITE_FOOTER = HwParam(True)

    @override
    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.i = self.AXI_CLS()
        self.o = HwIOStructRdVld()._m()
        self.o.T = HBits(32)

    @override
    @hlsBytecode
    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        o = PyBytecodeInPreproc(self.o)

        while b1:
            i.readStartOfFrame()
            PyBytecodeBlockLabel("sof")
            v0 = i.read(HBits(16))
            if v0.data._eq(3):
                PyBytecodeBlockLabel("case3B")
                v1a = PyBytecodeInPreproc(i.read(HBits(24)))
                hls.write(v1a.data._reinterpret_cast(o.T), o)

            elif v0.data._eq(4):
                PyBytecodeBlockLabel("case4B")
                v1b = PyBytecodeInPreproc(i.read(HBits(32)))
                hls.write(v1b.data._reinterpret_cast(o.T), o),
 
            PyBytecodeBlockLabel("final1B")
            v2 = i.read(HBits(8))
            if self.WRITE_FOOTER:
                hls.write(v2.data._reinterpret_cast(o.T), o)

            i.readEndOfFrame()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = Axi4SParse2IfAndSequel()
    m.DATA_WIDTH = 48
    m.CLK_FREQ = int(1e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    p._debugExpandCompositeNodes = True
    print(to_rtl_str(m, target_platform=p))
