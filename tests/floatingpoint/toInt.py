from hwt.code import Concat, Or
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.defs import BIT
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from pyMathBitPrecise.bit_utils import mask, to_unsigned, to_signed
from tests.floatingpoint.fptypes import IEEE754Fp


# based on https://github.com/dawsonjon/fpu/blob/master/float_to_int/float_to_int.v
def IEEE754FpToInt(a: RtlSignalBase[IEEE754Fp], res: RtlSignalBase[Bits]):
    assert res._dtype.signed, (res._dtype, "implemented only for signed")
    fp_t: IEEE754Fp = a._dtype
    extendBitCnt = res._dtype.bit_length() - fp_t.MANTISSA_WIDTH - 1
    if extendBitCnt <= 0:
        raise NotImplementedError("Result has fewer bits than mantissa")
    res = Concat(BIT.from_py(1), a.mantissa, Bits(extendBitCnt).from_py(0))._signed()
    resW = res._dtype.bit_length()
    exponent = a.exponent
    maxVal = mask(resW - 1)
    minVal = to_signed(1 << resW - 1, resW)
    if a.exponent._eq(0):
        res = 0  # < 1
    else:
        overflow = BIT.from_py(False)

        if exponent > to_unsigned(resW - 2 + fp_t.EXPONENT_OFFSET, fp_t.EXPONENT_WIDTH):
            # higher than res max value
            overflow = True
        else:
            shBoudary = to_unsigned(resW - 3 + fp_t.EXPONENT_OFFSET, fp_t.EXPONENT_WIDTH)
            while (exponent < shBoudary) & (res != 0):
                exponent += 1
                res = (res._unsigned() >> 1)._signed() # not using >>= 1 because we need logical shift not arithmetic 
            if res[resW - 1]:
                # higher than res max value
                overflow = True

        if overflow:
            if a.sign:
                res = minVal
            else:
                res = maxVal
        else:
            res = a.sign._ternary(-res._signed(), res)

    return res
