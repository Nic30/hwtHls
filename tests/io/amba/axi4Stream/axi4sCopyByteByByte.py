#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaLoop import PyBytecodeLLVMLoopUnroll, \
    PyBytecodeStreamLoopUnroll
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInPreproc, \
    PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream


class Axi4SPacketCopyByteByByteHs(HwModule):
    """
    Cut off Ethernet and IPv4 header.
    """

    def hwConfig(self) -> None:
        self.DATA_WIDTH = HwParam(16)
        self.OUT_DATA_WIDTH = HwParam(8)
        self.USE_STRB = HwParam(True)
        self.UNROLL = HwParam(PyBytecodeStreamLoopUnroll)
        self.CLK_FREQ = HwParam(int(100e6))

    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = self.USE_STRB
            self.tx = HwIODataRdVld()._m()
            self.tx.DATA_WIDTH = self.OUT_DATA_WIDTH

    def doUnrolling(self):
        # if can not be placed directly in hls code loop because metadata would be added to a wrong branch instruction
        # it would be added to branch of "if-then" instead of parent loop
        if self.UNROLL is PyBytecodeStreamLoopUnroll:
            return PyBytecodeStreamLoopUnroll(self.rx)
        else:
            return self.UNROLL

    @hlsBytecode
    def mainThread(self, hls: HlsScope, rx: IoProxyAxi4Stream):
        assert self.OUT_DATA_WIDTH == 8
        while b1:
            PyBytecodeBlockLabel("bb.sof")
            rx.readStartOfFrame()
            # pass body to tx output
            while b1:
                PyBytecodeBlockLabel("bb.dataLoop")
                self.doUnrolling()
                d = PyBytecodeInPreproc(rx.read(HBits(8), reliable=False))
                hls.write(d.data, self.tx)
                if d._isEoF():
                    PyBytecodeBlockLabel("bb.rx.eof")
                    del d
                    break
                del d

            PyBytecodeBlockLabel("bb.eof")
            rx.readEndOfFrame()

    def hwImpl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls, rx)
        hls.addThread(mainThread)
        hls.compile()


class Axi4SPacketCopyByteByByte(HwModule):
    """
    Cut off Ethernet and IPv4 header.
    """

    def hwConfig(self) -> None:
        Axi4SPacketCopyByteByByteHs.hwConfig(self)

    def hwDeclr(self):
        addClkRstn(self)
        with self._hwParamsShared():
            self.rx = Axi4Stream()
            self.rx.USE_STRB = True
        self.tx: Axi4Stream = Axi4Stream()._m()
        self.tx.USE_STRB = True
        if self.OUT_DATA_WIDTH is None:
            self.tx.DATA_WIDTH = self.OUT_DATA_WIDTH = self.DATA_WIDTH
        else:
            self.tx.DATA_WIDTH = self.OUT_DATA_WIDTH

    @hlsBytecode
    def mainThread(self, rx: IoProxyAxi4Stream, tx: IoProxyAxi4Stream):
        while b1:
            PyBytecodeBlockLabel("bb.sof")
            # pass body to tx output
            rx.readStartOfFrame()
            tx.writeStartOfFrame()
            while b1:
                PyBytecodeBlockLabel("bb.dataLoop")
                Axi4SPacketCopyByteByByteHs.doUnrolling(self)
                d = PyBytecodeInPreproc(rx.read(HBits(8), reliable=False))  # PyBytecodeInPreproc is used because we want to access internal properties of data (_isEoF)
                if d._isValid():
                    PyBytecodeBlockLabel("bb.tx.write")
                    tx.write(d.data, eof=d._isEoF())
                # del d is not necessary is there to limit live of d variable which is useful during debug
                if d._isEoF():
                    PyBytecodeBlockLabel("bb.rx.eof")
                    # :note: avoid using masked write as it leads to less readable code and needs to be lowered anyway
                    del d
                    break
                del d

            PyBytecodeBlockLabel("bb.eof")
            # in reverse order because frame processing behaves a a lock on IO
            # and this order is required to prevent deadlock
            tx.writeEndOfFrame()
            rx.readEndOfFrame()

    def hwImpl(self):
        hls = HlsScope(self)
        rx = IoProxyAxi4Stream(hls, self.rx)
        tx = IoProxyAxi4Stream(hls, self.tx)
        mainThread = HlsThreadFromPy(hls, self.mainThread, rx, tx)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle

    m = Axi4SPacketCopyByteByByte()
    m.DATA_WIDTH = 64
    # m.UNROLL = False
    # m.OUT_DATA_WIDTH = 16
    # m.OUT_DATA_WIDTH = 8
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))

