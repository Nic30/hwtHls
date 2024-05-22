from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.math import log2ceil
from hwt.mainBases import RtlSignalBase
from hwt.synthesizer.vectorUtils import fitTo
from hwtHls.code import getMsb, zext, lshr, ctlz, hwUMin, shl
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodePreprocHwCopy, \
    PyBytecodeInline, PyBytecodeNoSplitSlices
from pyMathBitPrecise.bit_utils import mask
from tests.floatingpoint.fptypes import IEEE754Fp


# https://github.com/sudhamshu091/32-Verilog-Mini-Projects/blob/main/Floating%20Point%20IEEE%20754%20Addition%20Subtraction/Addition_Subtraction.v
def _denormalize(a: RtlSignalBase[IEEE754Fp]):
    # :note: contains expression only, no inlining required
    # mantissa now has +4 bits, exponent is 1 if number is subnormal
    isSubnormal = a._dtype.isSubnormal(a)
    aMantissa = Concat(~isSubnormal, a.mantissa, HBits(3).from_py(0))
    expWidth = a.exponent._dtype.bit_length()
    aExponent = zext(a.exponent, expWidth + 1)  # + a._dtype.EXPONENT_OFFSET_U
    _aExponent = isSubnormal._ternary(aExponent._dtype.from_py(1), aExponent)
    return (aMantissa, _aExponent)


@PyBytecodeInline
def _swap(aSign, aExponent, aMantissa, bSign, bExponent, bMantissa):
    copy = PyBytecodePreprocHwCopy
    _aSign = copy(aSign)
    _aExponent = copy(aExponent)
    _aMantissa = copy(aMantissa)
    aSign = bSign
    aExponent = bExponent
    aMantissa = bMantissa
    bSign = _aSign
    bExponent = _aExponent
    bMantissa = _aMantissa
    return aSign, aExponent, aMantissa, bSign, bExponent, bMantissa


@hlsBytecode
def IEEE754FpAdd(a: RtlSignalBase[IEEE754Fp], b: RtlSignalBase[IEEE754Fp], isSim=False):
    """
    based on https://github.com/dawsonjon/fpu/blob/master/adder/adder.v
    https://github.com/ucb-bar/berkeley-softfloat-3
    https://users.encs.concordia.ca/~asim/COEN_6501/Lecture_Notes/L4_Slides.pdf
    https://doi.org/10.1049/iet-cdt.2016.0200
    https://github.com/OpenXiangShan/fudian/blob/main/src/main/scala/fudian/FADD.scala
    """
    t: IEEE754Fp = a._dtype
    res = t.from_py(None)
    if t.isNaN(a) | t.isNaN(b):
        # if a is NaN or b is NaN return NaN
        res.sign = 1
        res.exponent = t.getSpecialExponent()
        res.mantissa = t.getNaNMantisa()

    elif t.isInf(a):
        # if a is inf return inf
        res.sign = a.sign
        res.exponent = t.getSpecialExponent()
        res.mantissa = 0
        if t.isInf(b) & (a.sign != b.sign):
            res.mantissa = t.getNaNMantisa()

    elif t.isInf(b):
        # if b is inf return inf
        res.sign = b.sign
        res.exponent = t.getSpecialExponent()
        res.mantissa = 0

    elif t.isZero(a) & t.isZero(b):
        res.sign = a.sign & b.sign
        res.exponent = 0
        res.mantissa = 0

    elif t.isZero(a):
        res = b

    elif t.isZero(b):
        res = a

    else:
        # :note: mantissa +4 bits, exponent still format with 0=
        aMantissa, aExponent = _denormalize(a)
        aSign = a.sign
        bMantissa, bExponent = _denormalize(b)
        bSign = b.sign

        if aExponent < bExponent:
            # swap to have number with larger exponent in a to avoid dual shifting logic
            if isSim:

                def copy(x):
                    return x

            else:
                copy = PyBytecodePreprocHwCopy

            aSign, aExponent, aMantissa, \
            bSign, bExponent, bMantissa = \
                copy(bSign), copy(bExponent), copy(bMantissa), \
                copy(aSign), copy(aExponent), copy(aMantissa)

        requiredShift = aExponent - bExponent
        del bExponent  # no longer  required
        if requiredShift < t.MANTISSA_WIDTH:
            # perform shit of b to scale it to the same exponent as a
            # accumulate all shifted out bits t bit0
            # (original align)
            bMantissaTmp = Concat(bMantissa, HBits(t.MANTISSA_WIDTH - 1).from_py(0))
            bMantissaTmp = lshr(bMantissaTmp, requiredShift[log2ceil(bMantissaTmp._dtype.bit_length() + 1):])
            PyBytecodeNoSplitSlices(bMantissaTmp)
            bMantissa = Concat(bMantissaTmp[:t.MANTISSA_WIDTH], bMantissaTmp[t.MANTISSA_WIDTH:] != 0)
            del requiredShift
            del bMantissaTmp

            # perform mantissa add
            # (add_0)
            sumTmp = HBits(aMantissa._dtype.bit_length() + 1).from_py(None)
            res.sign = aSign

            aMantissaTmp = Concat(BIT.from_py(0), aMantissa)
            bMantissaTmp = Concat(BIT.from_py(0), bMantissa)

            if aSign._eq(bSign):
                sumTmp = aMantissaTmp + bMantissaTmp
            elif aMantissa < bMantissa:
                sumTmp = bMantissaTmp - aMantissaTmp
                res.sign = bSign
            else:
                sumTmp = aMantissaTmp - bMantissaTmp

            del aMantissa
            del bMantissa

            # (original add_1)
            mantissaTmp = HBits(t.MANTISSA_WIDTH + 1).from_py(None)
            exponetTmp = aExponent
            if getMsb(sumTmp):
                mantissaTmp = sumTmp[:4]
                guard_bit = sumTmp[3]
                round_bit = sumTmp[2]
                sticky_bit = sumTmp[1] | sumTmp[0]
                exponetTmp += 1
            else:
                # ! must be in sumTmp[msb-1]
                sumWidth = sumTmp._dtype.bit_length()
                mantissaTmp = sumTmp[sumWidth - 1:3]
                guard_bit = sumTmp[2]
                round_bit = sumTmp[1]
                sticky_bit = sumTmp[0]

            # normalize
            # (original normalise_1)
            # shift mantissaTmp that there is 1 in MSB, if exponent allows it
            leadingZeroCnt = ctlz(mantissaTmp)
            PyBytecodeNoSplitSlices(leadingZeroCnt)
            shAmount = hwUMin(fitTo(leadingZeroCnt._unsigned(), exponetTmp), exponetTmp)
            _shAmount = shAmount[log2ceil(mantissaTmp._dtype.bit_length() + 1):]
            mantissaTmp = shl(Concat(mantissaTmp[:1], guard_bit), _shAmount)
            PyBytecodeNoSplitSlices(mantissaTmp)
            exponetTmp -= shAmount
            round_bit &= shAmount._eq(0)
            # while ~getMsb(mantissaTmp) & (exponetTmp > 1):
            #    exponetTmp -= 1
            #    mantissaTmp = Concat(mantissaTmp[:1], guard_bit)
            #    round_bit = round_bit._dtype.from_py(0)

            # (original normalise_2)
            if exponetTmp._eq(0):
                # zero and subnormals
                exponetTmp += 1
                exponetTmp = exponetTmp._dtype.from_py(1)
                mantissaTmp >>= 1
                guard_bit = mantissaTmp[0]
                sticky_bit |= round_bit

            # round (original round)
            if (guard_bit & (round_bit | sticky_bit | mantissaTmp[0])):
                if mantissaTmp._eq(mask(t.MANTISSA_WIDTH + 1) - 1):
                    exponetTmp += 1
                mantissaTmp += 1

            # handle overflows
            # (original pack)
            overflow = exponetTmp[:t.EXPONENT_WIDTH] != 0
            if overflow:
                # return inf
                res.mantissa = res.mantissa._dtype.from_py(0)
                res.exponent = res.exponent._dtype.from_py(mask(t.EXPONENT_WIDTH))
            else:
                res.exponent = exponetTmp[t.EXPONENT_WIDTH:]
                res.mantissa = mantissaTmp[t.MANTISSA_WIDTH:]
                if exponetTmp._eq(1):
                    if ~mantissaTmp[t.MANTISSA_WIDTH]:
                        res.exponent = res.exponent._dtype.from_py(0)
                        if mantissaTmp[t.MANTISSA_WIDTH:]._eq(0):
                            res.sign = res.sign._dtype.from_py(0)  # -a + a = +0.

        else:
            # other number is too small to affect result value
            res.sign = aSign
            res.exponent = aExponent[t.EXPONENT_WIDTH:]
            res.mantissa = aMantissa[t.MANTISSA_WIDTH + 3:3]

    return res
