from hwt.hdl.commonConstants import b1
from hwt.mainBases import RtlSignalBase
from hwtHls.code import zext
from hwtHls.frontend.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel, \
    PyBytecodeInline
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.fp.normalizeDenormalize import fpUnpack, fpNormalize, \
    fpRoundup, fpPack


@hlsBytecode
def IEEE754FpMul(a: RtlSignalBase[IEEE754Fp], b: RtlSignalBase[IEEE754Fp]):
    """
    based on https://github.com/dawsonjon/verilog-math/blob/master/ip_generator/float.py#L133
             https://github.com/dawsonjon/fpu/blob/master/multiplier/multiplier.v
    """
    t: IEEE754Fp = a._dtype
    res = t.from_py(None)
    mantissaT = res.mantissa._dtype
    if a.isNaN() | b.isNaN():
        PyBytecodeBlockLabel("IEEE754FpMul.isNaN")
        # if a is NaN or b is NaN return NaN
        res.sign = a.sign ^ b.sign
        res.exponent = t.getSpecialExponentHw()
        res.mantissa = t.getNaNMantisaHw()

    elif a.isInf():
        PyBytecodeBlockLabel("IEEE754FpMul.aIsInf")
        # if b is zero return NaN
        res.exponent = t.getSpecialExponentHw()
        if b.isZero():
            # if b is zero return NaN
            res.sign = b1
            res.mantissa = t.getNaNMantisaHw()
        else:
            # if a is inf return inf
            res.sign = a.sign ^ b.sign
            res.mantissa = mantissaT.from_py(0)

    elif b.isInf():
        PyBytecodeBlockLabel("IEEE754FpMul.bIsInf")
        res.exponent = t.getSpecialExponentHw()
        if a.isZero():
            # if a is zero return NaN
            res.sign = b1
            res.mantissa = t.getNaNMantisaHw()
        else:
            # if b is inf return inf
            res.sign = a.sign ^ b.sign
            res.mantissa = mantissaT.from_py(0)

    elif a.isZero() & b.isZero():
        # if a or b is zero return zero
        PyBytecodeBlockLabel("IEEE754FpMul.Is0")
        res.sign = a.sign & b.sign
        res.exponent = res.exponent._dtype.from_py(0)
        res.mantissa = mantissaT.from_py(0)

    else:
        PyBytecodeBlockLabel("IEEE754FpMul.compute")
        aMantissa, aExponent = fpUnpack(a, mantisaWidthIncrease=0, expWidthIncrease=2)
        bMantissa, bExponent = fpUnpack(b, mantisaWidthIncrease=0, expWidthIncrease=2)

        PyBytecodeBlockLabel("IEEE754FpMul.multiply_0")
        resExponent = aExponent + bExponent + 1 - -t.EXPONENT_OFFSET
        mulResWidth = 2 * (t.MANTISSA_WIDTH + 1)
        product = zext(aMantissa, mulResWidth) * zext(bMantissa, mulResWidth)
        mantissaTmp, exponetTmp, guard_bit, round_bit, sticky_bit = fpNormalize(product, t.MANTISSA_WIDTH, resExponent)
        PyBytecodeNoSplitSlices(mantissaTmp)

        PyBytecodeBlockLabel("IEEE754FpMul.round")
        mantissaRounded, exponetTmp = fpRoundup(
            t,
            exponetTmp,
            mantissaTmp[mulResWidth:mulResWidth - 1 - t.MANTISSA_WIDTH],  # top MANTISSA_WIDTH bits except MSB (which is 1)
            guard_bit, round_bit, sticky_bit)

        res.sign = a.sign ^ b.sign
        PyBytecodeInline(fpPack)(exponetTmp, mantissaRounded, res)

    return res
