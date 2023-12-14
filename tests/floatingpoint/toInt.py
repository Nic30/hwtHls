from hwt.code import Concat
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode.markers import PyBytecodeBlockLabel
from pyMathBitPrecise.bit_utils import mask, to_unsigned, to_signed
from tests.floatingpoint.fptypes import IEEE754Fp


# based on https://github.com/dawsonjon/fpu/blob/master/float_to_int/float_to_int.v
def IEEE754FpToInt(a: RtlSignalBase[IEEE754Fp], res: RtlSignalBase[Bits]):
    """
    :note: does not handle +-inf and NaN
    """
    fp_t: IEEE754Fp = a._dtype
    resIsSigned = res._dtype.signed
    extendBitCnt = res._dtype.bit_length() - fp_t.MANTISSA_WIDTH - 1
    if extendBitCnt <= 0:
        raise NotImplementedError("Result has fewer bits than mantissa")

    res = Concat(BIT.from_py(1), a.mantissa, Bits(extendBitCnt).from_py(0))
    if resIsSigned:
        res = res._signed()

    resW = res._dtype.bit_length()
    exponent = a.exponent
    if resIsSigned:
        minVal = to_signed(1 << resW - 1, resW)
        maxVal = mask(resW - 1)
    else:
        minVal = 0
        maxVal = mask(resW)

    if a.exponent < (-fp_t.EXPONENT_OFFSET - 1):
        res = 0  # < 1
    else:
        # if exponent would shift the MSB out of bits of result
        shBoudary = to_unsigned(resW - (4 if resIsSigned else 3) + fp_t.EXPONENT_OFFSET, fp_t.EXPONENT_WIDTH)
        overflow = exponent > shBoudary
        if overflow | (a.sign & (not resIsSigned)):
            if a.sign:
                res = minVal
            else:
                res = maxVal
        else:
            shift = exponent._dtype.from_py(shBoudary + 1) - exponent
            for sh in range(0, resW):
                PyBytecodeBlockLabel(f"normalization.sh{sh:d}")
                if shift._eq(sh):
                    break
                res = res._unsigned() >> 1  # not using >>= 1 because we need logical shift not arithmetic

            if resIsSigned:
                res = res._signed()
                res = a.sign._ternary(-res._signed(), res)

    return res
