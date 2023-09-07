#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc, \
    PyBytecodeLLVMLoopUnroll, PyBytecodeStreamLoopUnroll
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axiStream.proxy import IoProxyAxiStream
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream


class AxiSPacketCopyByteByByteHs(Unit):
    """
    Cut off Ethernet and IPv4 header.
    """

    def _config(self) -> None:
        self.DATA_WIDTH = Param(512)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.rx = AxiStream()
            self.rx.USE_STRB = True
            self.txBody = Handshaked()._m()
            self.txBody.DATA_WIDTH = 8

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxiStream):
        while BIT.from_py(1):
            rx.readStartOfFrame()
            # pass body to txBody output
            while BIT.from_py(1):
                PyBytecodeLLVMLoopUnroll(True, self.DATA_WIDTH // 8)
                d = PyBytecodeInPreproc(rx.read(Bits(8), reliable=False))
                hls.write(d.data, self.txBody)
                if d._isLast():
                    del d
                    break
                del d

            rx.readEndOfFrame()

    def _impl(self):
        hls = HlsScope(self)
        rx = IoProxyAxiStream(hls, self.rx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx)
        hls.addThread(mainThread)
        hls.compile()


class AxiSPacketCopyByteByByte(Unit):
    """
    Cut off Ethernet and IPv4 header.
    """

    def _config(self) -> None:
        self.DATA_WIDTH = Param(512)
        self.OUT_DATA_WIDTH = Param(None)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.rx = AxiStream()
            self.rx.USE_STRB = True
        self.txBody: AxiStream = AxiStream()._m()
        self.txBody.USE_STRB = True
        if self.OUT_DATA_WIDTH is None:
            self.txBody.DATA_WIDTH = self.OUT_DATA_WIDTH = self.DATA_WIDTH
        else:
            self.txBody.DATA_WIDTH = self.OUT_DATA_WIDTH

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxiStream, txBody: IoProxyAxiStream):
        while BIT.from_py(1):
            # pass body to txBody output
            rx.readStartOfFrame()
            txBody.writeStartOfFrame()
            while BIT.from_py(1):
                PyBytecodeStreamLoopUnroll(rx)
                d = PyBytecodeInPreproc(rx.read(Bits(8), reliable=False)) # PyBytecodeInPreproc is used because we want to access internal properties of data (_isLast)
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
        rx = IoProxyAxiStream(hls, self.rx)
        txBody = IoProxyAxiStream(hls, self.txBody)
        mainThread = HlsThreadFromPy(hls, self.mainThread, rx, txBody)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle
    u = AxiSPacketCopyByteByByte()
    u.DATA_WIDTH = 16
    u.OUT_DATA_WIDTH = 16
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(u, target_platform=p))

