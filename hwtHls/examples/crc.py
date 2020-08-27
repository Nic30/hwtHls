#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from hwt.synthesizer.vectorUtils import iterBits
from hwtHls.hls import Hls
from hwtLib.logic.crcComb import CrcComb
from hwtLib.logic.crcPoly import CRC_32
from pyMathBitPrecise.bit_utils import get_bit, bit_list_reversed_bits_in_bytes,\
    bit_list_reversed_endianity

class CrcCombHls(CrcComb):
    def _config(self):
        CrcComb._config(self)
        self.CLK_FREQ = 100e6
        self.setConfig(CRC_32)
        self.DATA_WIDTH = 8

    def _impl(self):
        with Hls(self, freq=self.CLK_FREQ) as hls:
            DW = int(self.DATA_WIDTH)
            # assert PW == DW
            polyBits, PW = self.parsePoly(self.POLY, self.POLY_WIDTH)
            # xorMatrix = buildCrcMatrix_dataMatrix(polyCoefs, PW, DW)
            # initXorMatrix = buildCrcMatrix_reg0Matrix(polyCoefs, PW, DW)
            XOROUT = int(self.XOROUT)
            _INIT = int(self.INIT)
            initBits = [get_bit(_INIT, i)
                        for i in range(PW)]
            finBits = [get_bit(XOROUT, i)
                       for i in range(PW)]

            inBits = list(iterBits(hls.io(self.dataIn)))

            if not self.IN_IS_BIGENDIAN:
                inBits = bit_list_reversed_endianity(inBits)

            outBits = iterBits(hls.io(self.dataOut))

            crcMatrix = self.buildCrcXorMatrix(DW, polyBits)
            res = self.applyCrcXorMatrix(
                crcMatrix, inBits,
                initBits, bool(self.REFIN))

            if self.REFOUT:
                res = list(reversed(res))
                finBits = bit_list_reversed_bits_in_bytes(finBits)

            for ob, b, fb in zip(outBits, res, finBits):
                ob(b ^ fb)
            #for outBit, inMask in zip(iterBits(self.dataOut),
            #                          xorMatrix):
            #    bit = None
            #    for m, b in zip(reversed(inMask),
            #                    iterBits(self.dataIn)):
            #        if m:
            #            b = hls.io(b)
            #            if bit is None:
            #                bit = b
            #            else:
            #                bit = bit ^ b
            #    assert bit is not None
            #
            #    hls.io(outBit)(bit)

if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform

    u = CrcCombHls()

    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
