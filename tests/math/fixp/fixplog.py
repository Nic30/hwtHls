#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Logarithm Law                       Formula                               Example
==================================  ===================================== ===========================
Product Law                         log_a(m) + log_a(n) = log_a(m*n)      log(2) + log(3) = log(6)
Quotient Law                        log_a(m) – log_a(n) = log_a(m/n)      log(12) – log(3) = log(4)
Power Law                           log_a(m*k) = k ·log_a(m)              log(9) = log(32) = 2log(3)
Inverse Logarithm Property          log_a(a*k) = k                        log2(8) = log2(23) = 3
Zero Law                            log_a(1) = 0                          log3(1) = 0
Logarithm of a Reciprocal           log_a(1/m) = -log_a(m)                log(1/2) = -log(2)
Identity Property of a Logarithm    log_a(a) = 1                          log5(5) = 1
Inverse Property of an Exponent     a**log_a(k) = k                       3**log3(5) = 5
Change of Base Law                  log_a(m) = log_c(m)/log_c(a)          log2(5) = log3(5)/log3(2)
Other logarithmic identities        log_a(a+b) = log_a(a) + log_a(1+b/a)
                                    log_a(c)*log_c(b)=log_a(b)

:note: The logarithm curve from [2,4) is the same as the one from [1,2),
just shifted up by 2 and scaled horizontally by 2.
Likewise the curve from [4,8) is scaled the same way.

log(x*2**p) = log(x) + p*log(2)
log2(x*2**p) = log2(x) + p*1
-log2(1.0 / x) = log2(x) for 0 < x < 1

R = (2**k) * (1 + x) where x lies in interval 0 ≤ x ≤ 1
log2(R) = k + log2(1 + x) 10.1109/ICEE.2017.7893425

Computation of logarithm on per byte basis does not seem to work as large error
accumulates when multiple tables are active at once
e.g. 9830, the 0.15 in Q16.16, 8bit addr tables
[102, 38, 0, 0] [6.672425341971495, 5.247927513443585, 0, 0]
log2_32bit: 11.92035285541508 vs math.log2 13.262975701227942

https://libc.llvm.org/headers/math/log.html
 
"""
import math
from typing import Union

from hwt.hdl.const import HConst
from hwt.hdl.types.bits import HBits
from hwt.hwParam import HwParam
from hwt.serializer.mode import serializeParamsUniq
from hwtHls.code import ctlz, zext, shl
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeInline
from tests.math.fixp.fixpConst import HFixedPointQConst
from tests.math.fixp.fixpRtlSignal import HFixedPointQRtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQ
from tests.math.componentGenerators._genericHwModules import _FpUnOpAluHwModule
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


# https://github.com/punzik/log2pipelined/blob/main/rtl/log2lut.sv
# # https://github.com/artemglukhov/FLOG_BFLOAT16/blob/master/bfloat_fpu_systemverilog/rtl/lampFPU_log.sv
# # https://digitalsystemdesign.in/implementation-of-logarithm-function/
#    https://www.mathworks.com/help/fixedpoint/ug/implement-fixed-point-log2-using-lookup-table.html
#    :note: this does not work e.g. for log2(255.00390625) == 7.9943755367974445 but function returns -0.994375450806122
# https://stackoverflow.com/questions/76908525/how-do-i-compute-a-fixed-point-binary-logarithm
# log2 cordic https://github.com/NiteshVLSI/Hyperbolic-CORDIC-Based-Architecture-for-Computing-Logarithm/blob/main/cordic2.py
#             https://github.com/NiteshVLSI/Hyperbolic-CORDIC-Based-Architecture-for-Computing-Logarithm/blob/main/README.md
def fixp_log2_generateTable(maxTableAddrWidth: int, frac_width: int):
    """
    Generate lookup tables for individual bit slices of input value
    scaled to be an integer.
    """
    # bit msb is unused as always 1, remaining bits are treated as fraction bits
    # :note: tables[0] is for least significant bits
    #   the value of lsb corresponds to 2 ** -(width - 1)
    tables = []
    for tableI in range(math.ceil(frac_width / maxTableAddrWidth)):
        tableScale = 2 ** -(frac_width - tableI * maxTableAddrWidth)
        table = []
        assert frac_width - tableI * maxTableAddrWidth >= 0
        tableAddrWidth = min(maxTableAddrWidth,
                             frac_width - tableI * maxTableAddrWidth)
        for i in range(2 ** tableAddrWidth):
            if i == 0:
                v = 0.
            else:
                v = math.log2(1 + i * tableScale)
            table.append(v)
            # print(f"t[{i:08b}]: {1 +i * tableScale:.08f} {v:.08f}")

        tables.append(table)

    return tables


class FixpLog2():

    def __init__(self, t: HFixedPointQ, maxTableAddrWidth: int):
        self.T = t
        self.maxTableAddrWidth = maxTableAddrWidth
        self.width = t.int_bit_length + t.frac_bit_length - 1
        # tables for positive powers are limited because if power exceeds some number of bits
        # it can not fit into result and is inf
        self.tables = fixp_log2_generateTable(maxTableAddrWidth, self.width)

    def fixplog2_tabularized_py(self, x: float):
        return float(self.fixplog2_tabularized(self.T.from_py(x)))

    def fixplog2_tabularized(self, x: Union[HFixedPointQConst, HFixedPointQRtlSignal]):
        """
        :note: The value of x is scaled to be an integer, then log is resolved using table for groups of bits,
            result is summed and log(scale) is subtracted
        :note: based on fixpexp_tabularized, the intermediate results are accumulated using + instead of * and there is no case for negative value
        """
        t: HFixedPointQ = x._dtype
        isSigned = t.signed
        _f = HFloatTmp.from_py
        width = self.width
        numWidth = t.int_bit_length + t.frac_bit_length
        maxTableAddrWidth = self.maxTableAddrWidth
        isCompileTimeEvaluated = isinstance(x, HConst)

        xRaw = x._reinterpret_cast(HBits(numWidth))
        # normalize to 1 in msb, treat rest of the number as fract part
        numLeadingZeros = ctlz(xRaw, is_zero_poison=True)
        xRaw = shl(xRaw, numLeadingZeros)
        PyBytecodeNoSplitSlices(xRaw)
        numLeadingZerosSigned = zext(numLeadingZeros, numLeadingZeros._dtype.bit_length() + 1)._signed()
        numLeadingZerosAsFAsInt = (numLeadingZerosSigned._dtype.from_py(t.int_bit_length - 1) - numLeadingZerosSigned)
        numLeadingZerosAsFAsFp = numLeadingZerosAsFAsInt._explicit_cast(t)
        numLeadingZerosAsF = numLeadingZerosAsFAsFp._explicit_cast(HFloatTmp)

        res = _f(0.0)
        res += numLeadingZerosAsF
        tables = self.tables
        # query each table with bits extracted from input value and compute sum of all results
        for tableI, table in enumerate(tables):
            # :note: there may be less items in "tables" because from some number the result is "inf" and
            #  the tables are not build for values pass this threshold
            bitSliceForThisTable = slice(min(width, (tableI + 1) * maxTableAddrWidth),
                                         (tableI * maxTableAddrWidth))
            xBits = xRaw[bitSliceForThisTable]
            if isCompileTimeEvaluated:
                xBits = int(xBits)
            else:
                # convert table from python to hw compatible type
                # so compiler does not work with each number separately
                table = HFloatTmp[len(table)].from_py(table)

            if t is None:
                assert isSigned, "There could be more tables for -x only if the x is signed"
                v = _f(0.0)
            else:
                v = table[xBits]
            # print((bitSliceForThisTable, xBits, v), end="\n" if tableI == len(tables) - 1 else ", ")
            del xBits  # delete because width may differ between iterations which would raise type error
            res += v  # all values in table are negative numbers

        return res._explicit_cast(t)


@serializeParamsUniq
class FixpLog2TabularizedHwModule(_FpUnOpAluHwModule):

    def hwConfig(self) -> None:
        _FpUnOpAluHwModule.hwConfig(self)
        self.T = HFixedPointQ(8, 16)
        self.MAX_TABLE_ADDR_WIDTH = HwParam(8)

    def hwDeclr(self) -> None:
        _FpUnOpAluHwModule.hwDeclr(self)

        fixplog2 = FixpLog2(self.T, self.MAX_TABLE_ADDR_WIDTH)

        @hlsBytecode
        def _FN(x, loopPragmaGetter=lambda: None):
            return PyBytecodeInline(fixplog2.fixplog2_tabularized)(x)

        self.FN = _FN


def debug():
    T = HFixedPointQ(8, 8)
    maxErr = 0.0
    maxErrPoint = None
    maxTableAddrWidth = 8
    # scale = 2 ** -8
    fixplog2 = FixpLog2(T, maxTableAddrWidth)
    # test_data = [i * scale for i in range(1, 2 ** 16)]
    test_data = [ 1, 2, 4, 5, 6, 8,
                  3,
                  15,
                  0.125,
                  0.25,
                  0.3,
                  0.5,
                  0.75,
                  0.01,
                  1.5, 5.75
                 ]
    for x in test_data:
        res = float(fixplog2.fixplog2_tabularized_py(x))
        ref = math.log2(x)
        err = math.fabs(res - ref)
        print(f"x:{x:.08f},  log2(x):{ref:.08f}, fixplog2:{res:.08f}, err:{err:.08f}")
        if err > maxErr:
            maxErr = err
            maxErrPoint = x
    if maxErrPoint is not None:
        print("point:", maxErrPoint, " maxErr:", maxErr, "ref:", math.log2(maxErrPoint), fixplog2.fixplog2_tabularized_py(maxErrPoint))


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.virtual import VirtualHlsPlatform
    from hwtHls.platform.debugBundle import HlsDebugBundle, LLVM_CLI_COMMON_OPTS
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.installMathLib import installMathLibComponentGenerators

    m = FixpLog2TabularizedHwModule()
    m.CLK_FREQ = int(70e6)
    platform = Artix7Fast(debugFilter=HlsDebugBundle.ALL_RELIABLE,
                          llvmCliArgs=[
                              # LLVM_CLI_COMMON_OPTS.PRINT_BEFORE_ALL,
                              # LLVM_CLI_COMMON_OPTS.PRINT_CHANGED,
                          ]
                          )
    installMathLibComponentGenerators(platform)
    print(to_rtl_str(m, target_platform=platform))
    # debug()

