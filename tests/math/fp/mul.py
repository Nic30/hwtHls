from hwt.mainBases import RtlSignalBase
from hwtHls.code import zext
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.pragmaInstruction import PyBytecodeNoSplitSlices
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeBlockLabel, \
    PyBytecodeInline
from tests.math.fp.fptypes import IEEE754Fp
from tests.math.fp.normalizeDenormalize import _denormalize, fpNormalize, \
    fpRoundup, fpPack


@hlsBytecode
def IEEE754FpMul(a: RtlSignalBase[IEEE754Fp], b: RtlSignalBase[IEEE754Fp]):
    """
    based on https://github.com/dawsonjon/verilog-math/blob/master/ip_generator/float.py#L133
             https://github.com/dawsonjon/fpu/blob/master/multiplier/multiplier.v
    """
    t: IEEE754Fp = a._dtype
    res = t.from_py(None)
    if t.isNaN(a) | t.isNaN(b):
        PyBytecodeBlockLabel("IEEE754FpMul.isNaN")
        # if a is NaN or b is NaN return NaN
        res.sign = a.sign ^ b.sign
        res.exponent = t.getSpecialExponent()
        res.mantissa = t.getNaNMantisa()

    elif t.isInf(a):
        PyBytecodeBlockLabel("IEEE754FpMul.aIsInf")
        # if b is zero return NaN
        res.exponent = t.getSpecialExponent()
        if t.isZero(b):
            # if b is zero return NaN
            res.sign = 1
            res.mantissa = t.getNaNMantisa()
        else:
            # if a is inf return inf
            res.sign = a.sign ^ b.sign
            res.mantissa = 0

    elif t.isInf(b):
        PyBytecodeBlockLabel("IEEE754FpMul.bIsInf")
        res.exponent = t.getSpecialExponent()
        if t.isZero(a):
            # if a is zero return NaN
            res.sign = 1
            res.mantissa = t.getNaNMantisa()
        else:
            # if b is inf return inf
            res.sign = a.sign ^ b.sign
            res.mantissa = 0

    elif t.isZero(a) & t.isZero(b):
        # if a or b is zero return zero
        PyBytecodeBlockLabel("IEEE754FpMul.Is0")
        res.sign = a.sign & b.sign
        res.exponent = 0
        res.mantissa = 0

    else:
        PyBytecodeBlockLabel("IEEE754FpMul.compute")
        aMantissa, aExponent = _denormalize(a, mantisaWidthIncrease=0, expWidthIncrease=2)
        bMantissa, bExponent = _denormalize(b, mantisaWidthIncrease=0, expWidthIncrease=2)

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
