from hwt.code import Concat
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwtHls.code import lshr
from hwtHls.frontend.pyBytecode.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode.pragmaInstruction import PyBytecodeNoSplitSlices
from pyMathBitPrecise.bit_utils import mask, to_unsigned, to_signed
from tests.floatingpoint.fptypes import IEEE754Fp
from hwt.math import log2ceil


# based on https://github.com/dawsonjon/fpu/blob/master/float_to_int/float_to_int.v
def IEEE754FpToInt(a: RtlSignalBase[IEEE754Fp], res: RtlSignalBase[HBits], dbgUseIntrinsicSh=True):
    """
    :note: does not handle +-inf and NaN
    :param dbgUseIntrinsicSh: switch between a/lshr and shift implemented in loop
    """
    fp_t: IEEE754Fp = a._dtype
    resIsSigned = res._dtype.signed
    extendBitCnt = res._dtype.bit_length() - fp_t.MANTISSA_WIDTH - 1
    if extendBitCnt <= 0:
        raise NotImplementedError("Result has fewer bits than mantissa")

    res = Concat(BIT.from_py(1), a.mantissa, HBits(extendBitCnt).from_py(0))
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
            if dbgUseIntrinsicSh:
                resBitCntTyWidth = log2ceil(resW + 1)
                if resBitCntTyWidth < shift._dtype.bit_length():
                    # cut off bits which were used to detect overflows
                    _shift = shift[resBitCntTyWidth:]
                else:
                    _shift = shift
                res = lshr(res, _shift)
                PyBytecodeNoSplitSlices(res)
            else:
                for sh in range(0, resW):
                    PyBytecodeBlockLabel(f"normalization.sh{sh:d}")
                    if shift._eq(sh):
                        break
                    res = res._unsigned() >> 1  # not using >>= 1 because we need logical shift not arithmetic

            if resIsSigned:
                res = res._signed()
                res = a.sign._ternary(-res._signed(), res)

    return res
