#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.math import log2ceil
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.io.amba.axi4Stream.proxy import IoProxyAxi4Stream
from hwtHls.scope import HlsScope
from hwtLib.amba.axi4s import Axi4Stream
from hwtLib.types.ctypes import uint16_t
from tests.io.amba.axi4Stream.axisPacketCntr import Axi4SPacketCntr


class Axi4SPacketByteCntr0(Axi4SPacketCntr):
    """
    Counts a total number of bytes in any word seen.
    """

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._hwParamsShared():
            self.i = Axi4Stream()
            self.i.USE_STRB = True
            self.byte_cnt: HwIODataRdVld = HwIODataRdVld()._m()
            self.byte_cnt.DATA_WIDTH = 16

    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        byte_cnt = uint16_t.from_py(0)
        i.readStartOfFrame()
        while BIT.from_py(1):
            # end of frame is ignored
            for strbBit in i.read(self.i.data._dtype).strb:
                if strbBit:
                    # There the problem is that we do not have the information that the sequence of 1 in mask
                    # is consistent and we have to create a circuit with len(strb) adders which will add 1 if bit
                    # is set as written.
                    # This leads to high resource consumption for wide interfaces.
                    byte_cnt += 1
            hls.write(byte_cnt, self.byte_cnt)


class Axi4SPacketByteCntr1(Axi4SPacketByteCntr0):

    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        byte_cnt = uint16_t.from_py(0)
        i.readStartOfFrame()
        while BIT.from_py(1):
            wordByteCnt = HBits(log2ceil(self.i.strb._dtype.bit_length() + 1), signed=False).from_py(0)
            # this for is just MUX
            for i, strbBit in enumerate(i.read(self.i.data._dtype).strb):
                if strbBit:
                    # There we generate ROM of len(strb) values where item is selected based on last 1 bit in srtb
                    # This would not work if the prefix of strb contains some 0 bits before first 1.
                    wordByteCnt = i + 1
            # there is just 1 adder
            byte_cnt += wordByteCnt._reinterpret_cast(byte_cnt._dtype)
            hls.write(byte_cnt, self.byte_cnt)


class Axi4SPacketByteCntr2(Axi4SPacketByteCntr0):

    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        byte_cnt = uint16_t.from_py(0)
        strbWidth = self.i.strb._dtype.bit_length()
        i.readStartOfFrame()
        while BIT.from_py(1):
            wordByteCnt = HBits(log2ceil(strbWidth + 1), signed=False).from_py(strbWidth)
            # this for is just MUX
            for i, strbBit in enumerate(i.read(self.i.data._dtype).strb):
                if ~strbBit:
                    wordByteCnt = i
                    break

            # there is just 1 adder
            byte_cnt += wordByteCnt._reinterpret_cast(byte_cnt._dtype)
            hls.write(byte_cnt, self.byte_cnt)


class Axi4SPacketByteCntr3(Axi4SPacketByteCntr1):

    def mainThread(self, hls: HlsScope, i: IoProxyAxi4Stream):
        byte_cnt = uint16_t.from_py(0)
        strbWidth = self.i.strb._dtype.bit_length()
        i.readStartOfFrame()
        while BIT.from_py(1):
            # PyBytecodeInPreproc is used because otherwise 
            # the read object is converted to a RtlSignal because word= is a store to a word variable
            word = PyBytecodeInPreproc(i.read(self.i.data._dtype))
            wordByteCnt = HBits(log2ceil(strbWidth + 1), signed=False).from_py(strbWidth)
            # this for is just MUX
            for i, strbBit in enumerate(word.strb):
                if ~strbBit:  # [TODO] preproc variable divergence dependent on hw evaluated value
                    wordByteCnt = i
                    break

            # there is just 1 adder
            byte_cnt += wordByteCnt._reinterpret_cast(byte_cnt._dtype)
            if word.last:
                hls.write(byte_cnt, self.byte_cnt)
                byte_cnt = 0


if __name__ == "__main__":
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwt.synth import to_rtl_str
    from hwtHls.platform.platform import HlsDebugBundle

    m = Axi4SPacketByteCntr1()
    m.DATA_WIDTH = 16
    m.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)
    print(to_rtl_str(m, target_platform=p))
