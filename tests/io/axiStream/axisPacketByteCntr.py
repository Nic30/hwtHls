from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Handshaked
from hwt.interfaces.utils import addClkRstn
from hwt.math import log2ceil
from hwtHls.frontend.ast.statementsRead import IN_STREAM_POS
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInPreproc
from hwtHls.scope import HlsScope
from hwtLib.amba.axis import AxiStream
from hwtLib.types.ctypes import uint16_t
from tests.io.axiStream.axisPacketCntr import AxiSPacketCntr


class AxiSPacketByteCntr0(AxiSPacketCntr):
    """
    Counts a total number of bytes in any word seen.
    """

    def _declr(self):
        addClkRstn(self)
        self.clk.FREQ = self.CLK_FREQ
        with self._paramsShared():
            self.i = AxiStream()
            self.i.USE_STRB = True
            self.byte_cnt: Handshaked = Handshaked()._m()
            self.byte_cnt.DATA_WIDTH = 16

    def mainThread(self, hls: HlsScope):
        byte_cnt = uint16_t.from_py(0)
        while BIT.from_py(1):
            for strbBit in hls.read(self.i, self.i.data._dtype,
                                    inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END).strb:
                if strbBit:
                    # There the problem is that we do not have the information that the sequence of 1 in mask
                    # is consistent and we have to create a circuit with len(strb) adders which will add 1 if bit
                    # is set as written.
                    # This leads to high resource consumption for wide interfaces.
                    byte_cnt += 1
            hls.write(byte_cnt, self.byte_cnt)


class AxiSPacketByteCntr1(AxiSPacketByteCntr0):

    def mainThread(self, hls: HlsScope):
        byte_cnt = uint16_t.from_py(0)
        while BIT.from_py(1):
            wordByteCnt = Bits(log2ceil(self.i.strb._dtype.bit_length() + 1), signed=False).from_py(0)
            # this for is just MUX
            for i, strbBit in enumerate(
                    hls.read(self.i, self.i.data._dtype,
                             inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END).strb
                    ):
                if strbBit:
                    # There we generate ROM of len(strb) values where item is selected based on last 1 bit in srtb
                    # This would not work if the prefix of strb contains some 0 bits before first 1.
                    wordByteCnt = i + 1
            # there is just 1 adder
            byte_cnt += wordByteCnt._reinterpret_cast(byte_cnt._dtype)
            hls.write(byte_cnt, self.byte_cnt)


class AxiSPacketByteCntr2(AxiSPacketByteCntr0):

    def mainThread(self, hls: HlsScope):
        byte_cnt = uint16_t.from_py(0)
        strbWidth = self.i.strb._dtype.bit_length()
        while BIT.from_py(1):
            wordByteCnt = Bits(log2ceil(strbWidth + 1), signed=False).from_py(strbWidth)
            # this for is just MUX
            for i, strbBit in enumerate(
                    hls.read(self.i, self.i.data._dtype,
                             inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END).strb
                    ):
                if ~strbBit:
                    wordByteCnt = i
                    break

            # there is just 1 adder
            byte_cnt += wordByteCnt._reinterpret_cast(byte_cnt._dtype)
            hls.write(byte_cnt, self.byte_cnt)


class AxiSPacketByteCntr3(AxiSPacketByteCntr1):

    def mainThread(self, hls: HlsScope):
        byte_cnt = uint16_t.from_py(0)
        strbWidth = self.i.strb._dtype.bit_length()
        while BIT.from_py(1):
            # PyBytecodeInPreproc is used because otherwise 
            # the read object is converted to a RtlSignal because word= is a store to a word variable
            word = PyBytecodeInPreproc(
                    hls.read(self.i, self.i.data._dtype,
                             inStreamPos=IN_STREAM_POS.BEGIN_OR_BODY_OR_END))
            wordByteCnt = Bits(log2ceil(strbWidth + 1), signed=False).from_py(strbWidth)
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
    from hwt.synthesizer.utils import to_rtl_str

    u = AxiSPacketByteCntr1()
    u.DATA_WIDTH = 16
    u.CLK_FREQ = int(100e6)
    p = VirtualHlsPlatform(debugDir="tmp")
    print(to_rtl_str(u, target_platform=p))
