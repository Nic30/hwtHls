from typing import Union, Optional

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.const import HConst
from hwt.hdl.types.bitConstFunctions import AnyHBitsValue
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwtHls.code import zext, ctlz, shl, hwUMin
from hwtHls.frontend.pragmaPreproc import PyBytecodeBlockLabel
from hwtHls.frontend.pyBytecode import hlsBytecode
from pyMathBitPrecise.bit_utils import mask
from tests.math.fp.fptypes import IEEE754Fp


# https://github.com/sudhamshu091/32-Verilog-Mini-Projects/blob/main/Floating%20Point%20IEEE%20754%20Addition%20Subtraction/Addition_Subtraction.v
@hwt_expr_producer
def fpUnpack(a: RtlSignalBase[IEEE754Fp], mantisaWidthIncrease=3, expWidthIncrease=1) -> tuple[AnyHBitsValue, AnyHBitsValue]:
    """
    Transform mantissa and exponent in format where mantissa MSB is 1
    and both mantissa and exponent have sufficient bit width to not overflow 
    
    :note: mantissa +4 bits "MSB 1, mantissa, round, sticky", 
    :note: exponent is in the biased form
    :note: handles subnormal numbers (adds 1 to MSB)
    """
    # :note: contains expression only, no inlining required
    # mantissa now has +4 bits, exponent is 1 if number is subnormal
    isSubnormal = a.isSubnormal()
    # MSB is set to 1 for normal numbers and is 0
    if mantisaWidthIncrease:
        aMantissa = Concat(~isSubnormal, a.mantissa, HBits(mantisaWidthIncrease).from_py(0))
    else:
        aMantissa = Concat(~isSubnormal, a.mantissa)

    expWidth = a.exponent._dtype.bit_length()
    aExponent = zext(a.exponent, expWidth + expWidthIncrease)  # + a._dtype.EXPONENT_OFFSET_U
    _aExponent = isSubnormal._ternary(aExponent._dtype.from_py(1), aExponent)
    return (aMantissa, _aExponent)


@hwt_expr_producer
def fpNormalize(denormalMantissa: RtlSignalBase[HBits],
                MANTISSA_WIDTH: int,
                exponent: RtlSignalBase[HBits],
                underflowAmount: Optional[RtlSignalBase[HBits]]=None) \
                ->tuple[AnyHBitsValue, AnyHBitsValue, AnyHBitsValue, AnyHBitsValue, AnyHBitsValue]:
    """
    shift mantissa so MSB is 1, but not if it would make the exponent less than the
    minimum (0) in this case leave the number denormalized

    :note: exponent is in its native form (biased form)
    :note: subnormal numbers are supported 
    
    :param MANTISSA_WIDTH: width of mantissa in original FP type
    :param underflowAmount: amount of underflow specifies
        how many right shift amount for mantissa and a value
        to be substracted from exponent, however min exponent
        of 0 must be preserved and the number may become
        subnormal instead.
    """
    DW = denormalMantissa._dtype.bit_length()
    assert DW > MANTISSA_WIDTH + 1, (denormalMantissa, DW, MANTISSA_WIDTH)
    if underflowAmount:
        raise NotImplementedError()
    leadingZeroCnt = ctlz(denormalMantissa)
    # :note: if underflowAmount != 0, exponent is expected to be 0
    shiftAmount = hwUMin(exponent, leadingZeroCnt, autoExtend=True)  # assert saturation at 0
    mantissa = shl(denormalMantissa, shiftAmount[leadingZeroCnt._dtype.bit_length():])
    exponent = exponent - shiftAmount

    # mantissa in format "1, mantissa<MANTISSA_WIDTH>, ..."
    mantisaLsbIndex = DW - MANTISSA_WIDTH - 2  # -1 because of MSB 1, -1 because of size to index
    guard_bit = mantissa[mantisaLsbIndex]
    round_bit = mantissa[mantisaLsbIndex - 1]
    sticky_bit = mantissa[mantisaLsbIndex - 2:] != 0

    return mantissa, exponent, guard_bit, round_bit, sticky_bit


_bitTy = Union[bool, HConst[BIT], RtlSignalBase[BIT]]


@hwt_expr_producer
def fpRoundup(t: IEEE754Fp,
              exponetTmp: Union[HConst[HBits], RtlSignalBase[HBits]],
              mantissaTmp: Union[HConst[HBits], RtlSignalBase[HBits]],
              guard_bit: _bitTy, round_bit:_bitTy, sticky_bit:_bitTy):
    """
    https://pages.cs.wisc.edu/~markhill/cs354/Fall2008/notes/flpt.apprec.html
    https://stackoverflow.com/questions/8981913/how-to-perform-round-to-even-with-floating-point-numbers
    """
    assert mantissaTmp._dtype.bit_length() == t.MANTISSA_WIDTH + 1, (mantissaTmp._dtype, t.MANTISSA_WIDTH, mantissaTmp)
    if isinstance(guard_bit, (int, bool)):
        guard_bit = BIT.from_py(guard_bit)

    roundUp = guard_bit & (round_bit | sticky_bit | mantissaTmp[0])
    overflow = roundUp & mantissaTmp._eq(mask(t.MANTISSA_WIDTH + 1) - 1)  # is max value (and +1 would cause overflow)

    return (
        roundUp._ternary(mantissaTmp + 1, mantissaTmp),
        overflow._ternary(exponetTmp + 1, exponetTmp)
    )


@hlsBytecode
def fpPack(exponetTmp: RtlSignalBase[HBits], mantissaTmp: RtlSignalBase[HBits], res: RtlSignalBase[IEEE754Fp]):
    """
    handle overflows during conversion of wider exponent/mantissa to result
    """
    t = res._dtype
    overflow = exponetTmp[:t.EXPONENT_WIDTH] != 0
    if overflow:
        PyBytecodeBlockLabel("IEEE754FpAdd.overflow")
        # return inf
        res.mantissa = res.mantissa._dtype.from_py(0)
        res.exponent = res.exponent._dtype.from_py(mask(t.EXPONENT_WIDTH))
    else:
        PyBytecodeBlockLabel("IEEE754FpAdd.noOverflow")
        res.exponent = exponetTmp[t.EXPONENT_WIDTH:]
        res.mantissa = mantissaTmp[t.MANTISSA_WIDTH:]
        if exponetTmp._eq(1):
            if ~mantissaTmp[t.MANTISSA_WIDTH]:
                res.exponent = res.exponent._dtype.from_py(0)
                if mantissaTmp[t.MANTISSA_WIDTH:]._eq(0):
                    res.sign = res.sign._dtype.from_py(0)  # -a + a = +0.

