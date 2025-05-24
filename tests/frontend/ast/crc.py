#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import List

from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.vectorUtils import iterBits
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from hwtLib.logic.crcComb import CrcComb
from hwtLib.logic.crcPoly import CRC_32
from pyMathBitPrecise.bit_utils import get_bit, bit_list_reversed_bits_in_bytes, \
    bit_list_reversed_endianity


class CrcCombHls(CrcComb):

    @override
    def hwConfig(self):
        CrcComb.hwConfig(self)
        self.CLK_FREQ = 100e6
        self.setConfig(CRC_32)
        self.DATA_WIDTH = 8

    @override
    def hwDeclr(self):
        CrcComb.hwDeclr(self)

    @override
    def hwImpl(self):
        hls = HlsScope(self)

        def constructCrc(inVec: HBitsRtlSignal):
            DW = int(self.DATA_WIDTH)
            # assert PW == DW
            polyBits, PW = self.parsePoly(self.POLY, self.POLY_WIDTH)
            # xorMatrix = buildCrcMatrix_dataMatrix(polyCoefs, PW, DW)
            # initXorMatrix = buildCrcMatrix_reg0Matrix(polyCoefs, PW, DW)
            XOROUT = int(self.XOROUT)
            _INIT = int(self.INIT)
            initBits: List[int] = [get_bit(_INIT, i) for i in range(PW)]
            finBits: List[int] = [get_bit(XOROUT, i) for i in range(PW)]

            inBits = list(iterBits(inVec))
            if not self.IN_IS_BIGENDIAN:
                # we need to process lower byte first
                inBits = bit_list_reversed_endianity(inBits, extend=False)

            crcMatrix = self.buildCrcXorMatrix(DW, polyBits)
            res = self.applyCrcXorMatrix(
                crcMatrix, inBits,
                initBits, bool(self.REFIN))

            if self.REFOUT:
                res = list(reversed(res))
                finBits = bit_list_reversed_bits_in_bytes(finBits)
            return res, finBits

        def mainThread():
            while b1:
                dataIn = hls.read(self.dataIn).data
                res, finBits = constructCrc(dataIn)
                result = Concat(*(b ^ fb for  b, fb in reversed(tuple(zip(res, finBits))))) # reversed because Concat args in MSB first format
                hls.write(result, self.dataOut)

        hls.addThread(HlsThreadFromPy(hls, mainThread))
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtLib.logic.crcPoly import CRC_5_USB
    from hwtHls.platform.debugBundle import HlsDebugBundle
    # :note: increasing of recursion limit is required for larger CRCs
    # import sys
    # sys.setrecursionlimit(10 ** 5)

    m = CrcCombHls()
    m.setConfig(CRC_5_USB)
    m.REFOUT = False
    m.CLK_FREQ = int(200e6)
    m.DATA_WIDTH = 8

    print(to_rtl_str(m, target_platform=VirtualHlsPlatform(debugFilter=HlsDebugBundle.ALL_RELIABLE)))
