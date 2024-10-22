#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from math import ceil, log10

from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hwIOs.std import HwIODataRdVld
from hwt.hwIOs.utils import addClkRstn
from hwt.hwModule import HwModule
from hwt.hwParam import HwParam
from hwt.math import log2ceil
from hwt.pyUtils.typingFuture import override
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeInPreproc
from hwtHls.frontend.pyBytecode.thread import HlsThreadFromPy
from hwtHls.scope import HlsScope
from tests.frontend.pyBytecode.stmWhile import TRUE


class BinToBcd(HwModule):
    """
    Convert binary to BCD (Binary coded decimal) format
    (BCD is a format where each 4 bites represents a single decimal digit 0-9)

    based on https://github.com/kb000/bin2bcd/blob/master/rtl/bin2bcd32.v

    .. hwt-autodoc::
    """

    @override
    def hwConfig(self):
        self.DATA_WIDTH = HwParam(8)
        self.FREQ = HwParam(int(100e6))

    @override
    def hwDeclr(self):
        addClkRstn(self)
        self.clk.FREQ = self.FREQ
        assert self.DATA_WIDTH > 0, self.DATA_WIDTH
        self.BCD_DIGITS = self.decadic_deciamls_for_bin(self.DATA_WIDTH)
        assert self.BCD_DIGITS > 0
        self.din = HwIODataRdVld()
        self.din.DATA_WIDTH = self.DATA_WIDTH

        self.dout = HwIODataRdVld()._m()
        self.dout.DATA_WIDTH = self.BCD_DIGITS * 4

    @hlsBytecode
    @staticmethod
    def decadic_deciamls_for_bin(bin_width: int):
        return ceil(log10(2 ** bin_width))

    @hlsBytecode
    def mainThread(self, hls: HlsScope):
        DATA_WIDTH, BCD_DIGITS = \
        self.DATA_WIDTH, self.BCD_DIGITS

        while TRUE:
            bcdp = [
                hls.var(f"bcdp_{i:d}", HBits(4, signed=False))
                for i in range(BCD_DIGITS)]
            bcd_digits = [
                hls.var(f"bcd_digit_{i:d}", HBits(4, signed=False))
                for i in range(BCD_DIGITS)]
            # reset before first iteration
            for bcd in bcd_digits:
                bcd(0)

            bin_r = hls.read(self.din)
            bitcount = HBits(log2ceil(DATA_WIDTH + 1), signed=False).from_py(0)
            while bitcount != DATA_WIDTH:
                for bcdDigitI in range(BCD_DIGITS):
                    bcd = PyBytecodeInPreproc(bcd_digits[bcdDigitI])
                    bcdp_ = PyBytecodeInPreproc(bcdp[bcdDigitI])
                    if bcd >= 5:
                        bcdp_(bcd + 3)
                    else:
                        bcdp_(bcd)

                    prev = hls.var(f"prev_{bcdDigitI:d}", HBits(4))
                    if bcdDigitI == 0:
                        prev(bin_r[DATA_WIDTH - 1]._concat(HBits(3).from_py(0)))
                    else:
                        prev(bcdp[bcdDigitI - 1])

                    bcd((bcdp_ << 1) | (prev >> 3))

                bin_r <<= 1
                bitcount += 1

            hls.write(Concat(*reversed(bcd_digits)), self.dout)

    @override
    def hwImpl(self):
        hls = HlsScope(self)
        mainThread = HlsThreadFromPy(hls, self.mainThread, hls)
        hls.addThread(mainThread)
        hls.compile()


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.xilinx.artix7 import Artix7Medium
    from hwtHls.platform.platform import HlsDebugBundle

    m = BinToBcd()
    m.DATA_WIDTH = 8
    print(to_rtl_str(m, target_platform=Artix7Medium(debugFilter=HlsDebugBundle.ALL_RELIABLE)))

