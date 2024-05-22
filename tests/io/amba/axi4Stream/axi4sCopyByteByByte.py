#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwParam import HwParam
from hwt.hwModule import HwModule
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc, \
    PyBytecodeLLVMLoopUnroll, PyBytecodeStreamLoopUnroll
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream


class Axi4SPacketCopyByteByByteHs(HwModule):
    """
    Cut off Ethernet and IPv4 header.
    """

    def _config(self) -> None:
        self.DATA_WIDTH = HwParam(16)
        self.OUT_DATA_WIDTH = HwParam(8)
        self.USE_STRB = HwParam(True)
        self.UNROLL = HwParam(PyBytecodeStreamLoopUnroll)
        self.CLK_FREQ = HwParam(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = self.USE_STRB
            self.txBody = HwIODataRdVld()._m()
            self.txBody.DATA_WIDTH = self.OUT_DATA_WIDTH

    def doUnrolling(self):
        # if can not be placed directly in hls code loop because metadata would be added to a wrong branch instruction
        # it would be added to branch of "if-then" instead of parent loop
        if self.UNROLL is PyBytecodeStreamLoopUnroll:
            return PyBytecodeStreamLoopUnroll(self.rx)
        else:
            return self.UNROLL

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream):
        while BIT.from_py(1):
            rx.readStartOfFrame()
            # pass body to txBody output
            while BIT.from_py(1):
                self.doUnrolling()
                d = PyBytecodeInPreproc(rx.read(HBits(8), reliable=False))
                hls.write(d.data, self.txBody)
                if d._isLast():
                    del d
                    break
                del d

            rx.readEndOfFrame()

    def _impl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SPacketCopyByteByByte(HwModule):
    """
    Cut off Ethernet and IPv4 header.
    """

    def _config(self) -> None:
        Axi4SPacketCopyByteByByteHs._config(self)

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = True
        self.txBody: Axi4Stream = Axi4Stream()._m()
        self.txBody.USE_STRB = True
        if self.OUT_DATA_WIDTH is None:
            self.txBody.DATA_WIDTH = self.OUT_DATA_WIDTH = self.DATA_WIDTH
        else:
            self.txBody.DATA_WIDTH = self.OUT_DATA_WIDTH

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, txBody: IoProxyAxi4Stream):
        while BIT.from_py(1):
            # pass body to txBody output
            rx.readStartOfFrame()
            txBody.writeStartOfFrame()
            while BIT.from_py(1):
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = PyBytecodeInPreproc(rx.read(HBits(8), reliable=False))  # PyBytecodeInPreproc is used because we want to access internal properties of data (_isLast)
                txBody.write(d.data)
                # del d is not necessary is there to limit live of d variable which is useful during debug
                if d._isLast():
                    # :note: avoid using masked write as it leads to less readable code and needs to be lowered anyway
                    del d
                    break
                del d
            # in reverse order because frame processing behaves a a lock on IO
            # and this order is required to prevent deadlock
            txBody.writeEndOfFrame()
            rx.readEndOfFrame()

    def _impl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        txBody = IoProxyAxi4Stream(hls, self.txBody)
        mainThread = HlsThreadFromPy(hls, self.mainThread, rx, txBody)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    
    m = Axi4SPacketCopyByteByByteHs()
    m.DATA_WIDTH = 16
    m.UNROLL = False
    # m.OUT_DATA_WIDTH = 8
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))

