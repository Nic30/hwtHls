#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from hwt.synthesizer.vectorUtils import iterBits
from hwtHls.hlsStreamProc.streamProc import HlsStreamProc
from hwtLib.logic.crcComb import CrcComb
from hwtLib.logic.crcPoly import CRC_32
from pyMathBitPrecise.bit_utils import get_bit, bit_list_reversed_bits_in_bytes, \
    bit_list_reversed_endianity


class CrcCombHls(CrcComb):

    def _config(self):
        CrcComb._config(self)
        self.CLK_FREQ = 100e6
        self.setConfig(CRC_32)
        self.DATA_WIDTH = 8

    def _declr(self):
        CrcComb._declr(self)
        self.clk.FREQ = self.CLK_FREQ

    def _impl(self):
        hls = HlsStreamProc(self)
        DW = int(self.DATA_WIDTH)
        # assert PW == DW
        polyBits, PW = self.parsePoly(self.POLY, self.POLY_WIDTH)
        # xorMatrix = buildCrcMatrix_dataMatrix(polyCoefs, PW, DW)
        # initXorMatrix = buildCrcMatrix_reg0Matrix(polyCoefs, PW, DW)
        XOROUT = int(self.XOROUT)
        _INIT = int(self.INIT)
        initBits: List[int] = [get_bit(_INIT, i) for i in range(PW)]
        finBits: List[int] = [get_bit(XOROUT, i) for i in range(PW)]

        inBits = list(iterBits(hls.read(self.dataIn)))

        if not self.IN_IS_BIGENDIAN:
            inBits = bit_list_reversed_endianity(inBits)

        crcMatrix = self.buildCrcXorMatrix(DW, polyBits)
        res = self.applyCrcXorMatrix(
            crcMatrix, inBits,
            initBits, bool(self.REFIN))

        if self.REFOUT:
            res = list(reversed(res))
            finBits = bit_list_reversed_bits_in_bytes(finBits)

        result = hls.var("result", self.dataOut._dtype)
        outBits = iterBits(result)

        hls.thread(
            hls.While(True,
                *(
                    ob(b ^ fb)
                    for ob, b, fb in zip(outBits, res, finBits)
                ),
                hls.write(result, self.dataOut)
            )
        )


if __name__ == "__main__":
    from hwt.synthesizer.utils import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform

    u = CrcCombHls()
    u.CLK_FREQ = int(200e6)
    u.DATA_WIDTH = 128

    print(to_rtl_str(u, target_platform=VirtualHlsPlatform()))
