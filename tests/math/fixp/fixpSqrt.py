#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# https://github.com/dawsonjon/verilog-math/blob/master/ip_generator/float.py#L30
# https://github.com/dawsonjon/Chips-2.0/blob/master/examples/sqrt.c
# https://www.shironekolabs.com/posts/efficient-approximate-square-roots-and-division-in-verilog/
# https://github.com/openhwgroup/cvfpu
# https://github.com/akilm/FPU-IEEE-754/blob/main/srcs/sources/FloatingSqrt.v
# https://github.com/Xilinx/Vitis-HLS-Introductory-Examples/blob/2023.2/Modeling/fixed_point_sqrt/fxp_sqrt.h
# https://vhdlguru.blogspot.com/2020/12/synthesizable-clocked-square-root.html
# https://projectf.io/posts/square-root-in-verilog/
# rsqrt https://github.com/erinjense/rsqrt-vhdl
#       https://mrober.io/papers/rsqrt.pdf
#       https://www.fpgarelated.com/showarticle/1347.php?utm_source=chatgpt.com
# https://stackoverflow.com/a/4657849 https://stackoverflow.com/questions/4657468/fast-fixed-point-pow-log-exp-and-sqrt/4657849#4657849
# https://stackoverflow.com/questions/1100090/looking-for-an-efficient-integer-square-root-algorithm-for-arm-thumb2
from typing import Union

from hwt.code import Concat
from hwt.hdl.commonConstants import b1
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwtHls.code import zext
from hwtHls.frontend import hwrange.hwrange
from tests.math.fixp.fixpConst import HFixedPointQConst
from tests.math.fixp.fixpRtlSignal import HFixedPointQRtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQ

# @hlsBytecode
# def intSqrt(a: Union[HBitsConst, HBitsRtlSignal], iterationCnt:Optional[int]=None, loopPragmaGetter=lambda:None):
#    """
#    Non-restoring integer square root
#
#    Implementation of: https://doi.org/10.1109/ICCD.1996.563604
#    Based on: https://vhdlguru.blogspot.com/2020/12/synthesizable-clocked-square-root.html
#
#    :note:
#
#    """
#    width = a._dtype.bit_length()
#    if iterationCnt is None:
#        iterationCnt = width
#    resultWidth = width // 2
#    square_root = HBits(resultWidth).from_py(0)
#    remainder = HBits(resultWidth + 2).from_py(0)
#    for _ in hwrange(iterationCnt):
#        lhs = Concat(square_root, remainder[resultWidth + 1], b1)
#        rhs = Concat(remainder[resultWidth:0], a[width:width - 2])
#        # add or subtract as per this bit.
#        if remainder[resultWidth + 1]:
#            remainder = lhs + rhs
#        else:
#            remainder = lhs - rhs
#        a <<= 2
#
#        square_root = Concat(square_root[width // 2 - 1:0], ~remainder[width // 2 + 1])
#        loopPragmaGetter()
#
#    return square_root


def fixpSqrt(a: Union[HFixedPointQConst, HFixedPointQRtlSignal, HBitsConst, HBitsRtlSignal], loopPragmaGetter=lambda:None):
    """
    Longdiv alg. based integer square root
    :note: input of sqrt is called radicand
    
    Based on https://projectf.io/posts/square-root-in-verilog/
    """
    t = a._dtype
    width = t.bit_length()
    tRaw = HBits(width)
    assert not t.signed, ("must satisfy x >= 0, it can not be signed", t)
    if isinstance(t, HFixedPointQ):
        int_width = t.int_bit_length
        frac_width = t.frac_bit_length
    else:
        int_width = width
        frac_width = 0

    assert width == int_width + frac_width
    assert width % 2 == 0, ("must be a multiple of 2, for example, when working with 7 binary digits, you must set the width to 8", t, a, width)
    iterationCnt = (int_width + frac_width * 2) // 2

    bit2_t = HBits(2)
    b2_00 = bit2_t.from_py(0)
    b2_01 = bit2_t.from_py(0b01)
    square_root = tRaw.from_py(0)  # intermediate root (quotient)
    aRaw = a._reinterpret_cast(HBits(width))
    remainder = zext(aRaw[:width - 2], width + 2)  # accumulator (2 bits wider)
    x = Concat(aRaw[width - 2:], b2_00)  # radicand copy

    for _ in hwrange(iterationCnt):
        # sign test result (2 bits wider)
        test_res = remainder - Concat(square_root, b2_01)
        ac_topBits = tRaw.from_py(None)
        if test_res.getMsb():  # test_res >=0? (check MSB)
            ac_topBits = remainder[width:]
            square_root = square_root << 1
        else:
            ac_topBits = test_res[width:]
            square_root = Concat(square_root[width - 1:], b1)

        remainder = Concat(ac_topBits, x[:width - 2])
        x = Concat(x[width - 2:], b2_00)
        loopPragmaGetter()

    # rem = remainder[:2]  # undo the final shift
    return square_root._reinterpret_cast(t)

# def sqrt_fixed_point(num, frac_width):
#    """
#    Compute the square root of a fixed-point number `num` with `frac_width` fractional bits.
#    This implementation avoids using multiplication, division, and square root at runtime.
#
#    :param num: The fixed-point number (integer representation).
#    :param frac_width: The number of fractional bits in the fixed-point representation.
#    :return: The square root in fixed-point format (integer representation).
#    """
#    # Initialize the result to 0
#    result = 0
#    # We need to compute the integer square root. Start by considering the bit width.
#    bit_width = num.bit_length() + frac_width  # Total bit width of result
#
#    for i in range(bit_width - 1, -1, -1):
#        # Shift result left to make room for the next bit
#        result <<= 1
#        # We set a temporary value for the trial square
#        trial_result = result | (1 << i)
#
#        # The square of trial_result should be less than or equal to the original number
#        # We're using only bitwise comparisons, not multiplication
#        trial_square = trial_result >> frac_width  # We shift down to account for fixed-point
#        if (trial_square <= num):
#            result |= (1 << i)
#
#    return result

# @hlsBytecode
# def sqrt(x: Union[HBitsConst, RtlSignal[HBits]]):
#    """
#    based on https://github.com/tchoi8/verilog/blob/master/examples/sqrt.vl
#    """
#    inTy = x._dtype
#    bits = inTy.bit_length()
#
#    largest_number = (2 ** bits) - 1
#    largest_sqrt = math.ceil(math.sqrt(largest_number))
#    result_bits = int(math.ceil(math.log(largest_sqrt, 2.0)))
#    resTy = HBits(result_bits)
#
#    # acc holds the accumulated result, and acc2 is the accumulated
#    # square of the accumulated result.
#    acc = HBits(result_bits).from_py(0)
#    acc2 = HBits(bits + 1).from_py(0)
#
#    # guess holds the potential next values for acc, and guess2 holds
#    # the square of that guess. The guess2 calculation is a little bit
#    # subtle. The idea is that:
#    #
#    #      guess2 = (acc + bit) * (acc + bit)
#    #             = (acc * acc) + 2*acc*bit + bit*bit
#    #             = acc2 + 2*acc*bit + bit2
#    #             = acc2 + 2 * (acc<<bitl) + bit
#    #
#    # This works out using shifts because bit and bit2 are known to
#    # have only a single bit in them.
#    for bitl in hwrange(result_bits, 0, -1):
#        bit = resTy.from_py(1) << bitl
#        bit2 = inTy.from_py(1) << (bitl << 1)
#        guess  = acc | bit
#        guess2 = acc2 + bit2 + ((acc << bitl) << 1)
#        if guess2 <= x:
#            acc  = guess
#            acc2 = guess2
#
#
#    return acc


if __name__ == "__main__":
    from hwt.synth import to_rtl_str
    from hwtHls.platform.debugBundle import HlsDebugBundle
    from hwtHls.platform.xilinx.artix7 import Artix7Fast
    from tests.math.componentGenerators.fsqrt import FixpSqrtHwModule
    m = FixpSqrtHwModule()
    m.T = HBits(16)
    m.UNROLL_FACTOR = m.T.bit_length() // 2
    m.CLK_FREQ = int(100e6)
    print(to_rtl_str(m, target_platform=Artix7Fast()))  # {debugFilter=HlsDebugBundle.ALL_RELIABLE, HlsDebugBundle.DBG_23_arch}
