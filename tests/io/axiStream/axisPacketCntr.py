#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import VectSignal
from hwt.interfaces.utils import addClkRstn
from hwt.math import log2ceil
from hwt.synthesizer.param import Param
from hwt.synthesizer.unit import Unit
from hwtHls.hlsStreamProc.statementsIo import IN_STREAM_POS
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtHls.ssa.translation.fromPython.markers import PythonBytecodeInPreproc
from hwtHls.ssa.translation.fromPython.thread import HlsStreamProcPyThread
from hwtLib.amba.axis import AxiStream
from hwtLib.types.ctypes import uint16_t


class AxiSPacketCntr(Unit):

    def _config(self) -> None:
        self.DATA_WIDTH = Param(512)
        self.CLK_FREQ = Param(int(100e6))

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            self.pkt_cnt: VectSignal = VectSignal(16, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        pkts = uint16_t.from_py(0)
        while BIT.from_py(1):
            hls.write(pkts, self.pkt_cnt)
            word = PythonBytecodeInPreproc(# PythonBytecodeInPreproc is used because otherwise 
                                            # the read object is converted to a RtlSignal because word= is a store to a word variable
                hls.read(self.i, self.i.data._dtype,
                inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END))

            if word._isLast():
                pkts += 1

    def _impl(self):
        hls = HlsStreamProc(self)
        hls.thread(HlsStreamProcPyThread(hls, self.mainThread, hls))
        hls.compile()


class AxiSPacketByteCntr0(AxiSPacketCntr):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            self.i.USE_STRB = True
            self.byte_cnt: VectSignal = VectSignal(16, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        byte_cnt = uint16_t.from_py(0)
        while BIT.from_py(1):
            hls.write(byte_cnt, self.byte_cnt)
            for strbBit in hls.read(self.i, self.i.data._dtype,
                             inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END).strb:
                if strbBit:
                    # There the problem is that we do not have the information that the sequence of 1 in mask
                    # is consistent and we have to create a circuit with len(strb) adders which will add 1 if bit
                    # is set as written.
                    # This leads to high resource consumption for wide interfaces.
                    byte_cnt += 1


class AxiSPacketByteCntr1(AxiSPacketCntr):

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            self.i.USE_STRB = True
            self.byte_cnt: VectSignal = VectSignal(16, signed=False)._m()

    def mainThread(self, hls: HlsStreamProc):
        byte_cnt = uint16_t.from_py(0)
        while BIT.from_py(1):
            hls.write(byte_cnt, self.byte_cnt)
            wordBytes = Bits(log2ceil(self.i.strb._dtype.bit_length() + 1), signed=False).from_py(0)
            for i, strbBit in enumerate(
                    hls.read(self.i, self.i.data._dtype,
                             inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END).strb
                    ):
                if strbBit:
                    # There we generate ROM of len(strb) values where item is selected based on last 1 bit in srtb
                    # This would not work if the prefi of strb contains some 0 bits before first 1.
                    wordBytes = i + 1
            # there is just 1 adder
            byte_cnt += wordBytes._reinterpret_cast(byte_cnt._dtype)


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform, makeDebugPasses
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSPacketByteCntr0()
    u.DATA_WIDTH = 32
    p = VirtualHlsPlatform(**makeDebugPasses("tmp"))
    print(to_rtl_str(u, target_platform=p))
