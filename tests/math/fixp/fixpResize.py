import math
from typing import Union

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwt.hdl.commonConstants import b0
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwtHls.code import incrSat
from hwtHls.llvm.llvmIr import HFloatTmpRounding, HFloatTmpSaturation
from pyMathBitPrecise.bit_utils import mask, to_signed, to_unsigned
from tests.math.fixp.fixpTypes import HFixedPointQ


def fixp_resize_py(x: float, signed:bool,
                   inIntWidth: int, inFracWidth: int,
                   outIntWidth: int, outFracWidth: int,
                   roundingMode: HFloatTmpRounding,
                   saturationMode: HFloatTmpSaturation):
    """
    The same functionality as fixp_resize but for python float number.
    """
    inputScale = 2 ** inFracWidth
    shiftedValue = x * inputScale  # all number bits will be in the int part
    fracSizeDiff = outFracWidth - inFracWidth
    # scale shiftedValue so the lsb is bit 0 of output fractionpart
    shiftedValue *= 2 ** fracSizeDiff
    if fracSizeDiff < 0:
        # output fraction part is smaller, need truncation and rounding
        if roundingMode == HFloatTmpRounding.ROUND_HALF_EVEN:
            roundedValue = round(shiftedValue)
        elif roundingMode == HFloatTmpRounding.ROUND_HALF_UP:
            # https://stackoverflow.com/a/79758374
            if shiftedValue >= 0:
                roundedValue = int(shiftedValue + 0.5)
            else:
                roundedValue = int(shiftedValue - 0.5)
        elif roundingMode == HFloatTmpRounding.ROUND_DOWN:
            if shiftedValue > 0:
                roundedValue = math.floor(shiftedValue)
            else:
                roundedValue = math.ceil(shiftedValue)
        elif roundingMode == HFloatTmpRounding.ROUND_CEILING:
            roundedValue = math.ceil(shiftedValue)
        elif roundingMode == HFloatTmpRounding.ROUND_FLOOR:
            roundedValue = math.floor(shiftedValue)
        else:
            raise NotImplementedError("Invalid rounding mode:", roundingMode)

    if signed:
        maxOutputValue = (2 ** (outIntWidth + outFracWidth - 1)) - 1
        minOutputValue = -(2 ** (outIntWidth + outFracWidth - 1))
    else:
        maxOutputValue = (2 ** (outIntWidth + outFracWidth)) - 1
        minOutputValue = 0

    if saturationMode == HFloatTmpSaturation.SATURATE_INF:
        if roundedValue > maxOutputValue:
            finalValue = maxOutputValue
        elif roundedValue < minOutputValue:
            finalValue = minOutputValue
        else:
            finalValue = roundedValue

    elif saturationMode == HFloatTmpSaturation.SATURATE_NONE:
        roundedValue = int(roundedValue)
        outWidth = outIntWidth + outFracWidth
        roundedValue &= mask(outWidth)
        if signed:
            roundedValue = to_signed(roundedValue, outWidth)
        elif roundedValue < 0:
            roundedValue = to_unsigned(roundedValue, outWidth)

        finalValue = roundedValue
    else:
        finalValue = roundedValue

    outputScale = 2 ** outFracWidth
    finalValue = finalValue / outputScale

    return finalValue


def ConcatOptional(*msbFirstArgs):
    return Concat(*(a for a in msbFirstArgs if a is not None))


@hwt_expr_producer
def fixp_resize(value: Union[HBitsRtlSignal, HBitsConst],
                inTy: HFixedPointQ,
                outTy: HFixedPointQ,
                roundingOverride=None,
                saturationOverride=None) -> Union[HBitsRtlSignal, HBitsConst]:
    """
    Convert between HFixedPointQ values, applying saturation and rounding

    :attention: input value is of raw HBits type as well as output, HFixedPointQ is used only for configuration
        purposes and is not actually a native type of input or output value

    .. table:: Example of rounding to integers using the IEEE 754 rules
    
        =========================================== ========================= 
        Mode                                         Example value            
        =========================================== ========================= 
                                                     +11.5  +12.5 −11.5 −12.5 
        =========================================== ====== ====== ===== ===== 
         to nearest, ties to even (half_even)        +12.0  +12.0 −12.0 −12.0 
         to nearest, ties away from zero (half_up)   +12.0  +13.0 −12.0 −13.0 
         toward 0  (down)                            +11.0  +12.0 −11.0 −12.0 
         toward +∞ (ceil)                            +12.0  +13.0 −11.0 −12.0 
         toward −∞ (floor)                           +11.0  +12.0 −12.0 −13.0 
        =========================================== ====== ====== ===== ===== 

    .. table:: Example of rounding to integers using the IEEE 754 rules in binary

        ========================================== ========================================== ===================  =================== ====================== ======================
        Q8.1 (dec, hex, bin)                        rule                                       11.5, 17, 01011.1    12.5, 19, 01100.1   -11.5, e9, 1110100.1   -12.5, e7, 1110011.1
        ========================================== ========================================== ===================  =================== ====================== ======================
        to nearest, ties to even (half_even)        if round_bit && newLsb: x += 1; trunc(x)   12.0, 18, 01100.0    12.0, 18, 01100.0   −12.0, e8, 1110100.0   −12.0, e8, 1110100.0
        to nearest, ties away from zero (half_up)   if round_bit && x >= 0: x += 1; trunc(x)   12.0, 18, 01100.0    13.0, 1a, 01101.0   −12.0, e8, 1110100.0   −13.0, e6, 1110011.0
        toward 0  (down)                            if round_bit && x < 0: x += 1; trunc(x)    11.0, 16, 01011.0    12.0, 18, 01100.0   −11.0, ea, 1110101.0   −12.0, e8, 1110100.0
        toward +∞ (ceil)                            if round_bit: x += 1; trunc(x)             12.0, 18, 01100.0    13.0, 1a, 01101.0   −11.0, ea, 1110101.0   −12.0, e8, 1110100.0
        toward −∞ (floor)                           trunc(x)                                   11.0, 16, 01011.0    12.0, 18, 01100.0   −12.0, e8, 1110100.0   −13.0, e6, 1110011.0
        ========================================== ========================================== ===================  =================== ====================== ======================
    """

    # https://github.com/WangXuan95/FPGA-FixedPoint/blob/master/RTL/fixedpoint.v#L22
    # https://icshare.work/posts/understanding-rounding-and-saturation-in-hardward-design/
    assert value._dtype.bit_length() == inTy.bit_length(), (value._dtype, inTy)
    signed = inTy.signed
    # assert signed == outTy.signed, (inTy, outTy)
    if inTy == outTy:
        return value
    for cfg in (inTy.getHFloatTmpConfig(), outTy.getHFloatTmpConfig()):
        if cfg.hasIs0 or cfg.hasIs1 or cfg.hasIsInf or cfg.hasIsNaN:
            raise NotImplementedError(cfg, inTy, outTy, value)

    rounding = roundingOverride if roundingOverride is not None else inTy.rounding
    saturation = saturationOverride if saturationOverride is not None else inTy.saturation
    value = value._cast_sign(None)
    inInt = value[:inTy.frac_bit_length]
    if inTy.frac_bit_length:
        inFrac = value[inTy.frac_bit_length:]
    else:
        inFrac = None
    fracSizeDiff = outTy.frac_bit_length - inTy.frac_bit_length
    hasFrac = bool(outTy.frac_bit_length)
    if fracSizeDiff < 0:
        # output fraction part is smaller, need truncation and rounding
        outFrac = inFrac[:-fracSizeDiff] if hasFrac else None
        if rounding == HFloatTmpRounding.ROUND_FLOOR or (rounding == HFloatTmpRounding.ROUND_DOWN and not signed):
            pass  # just truncation
        else:
            # https://zipcpu.com/dsp/2017/07/22/rounding.html
            round_bit = inFrac[-fracSizeDiff - 1]  # most significant removed bit
            if rounding == HFloatTmpRounding.ROUND_HALF_EVEN:
                # nearest with ties going to nearest even integer. (c default)
                # if round_bit && newLsb: x += 1; trunc(x)
                addOneFlag = round_bit & (outFrac[0] if hasFrac else inInt[0])
            elif rounding == HFloatTmpRounding.ROUND_HALF_UP:
                #  nearest with ties going away from 0.
                # if round_bit && x > 0: x += 1; trunc(x)
                addOneFlag = round_bit & ~inInt[inInt._dtype.bit_length() - 1]
            elif rounding == HFloatTmpRounding.ROUND_DOWN:
                #  towards 0.
                # if round_bit && x < 0: x += 1; trunc(x)
                addOneFlag = round_bit & inInt[inInt._dtype.bit_length() - 1]
            elif rounding == HFloatTmpRounding.ROUND_CEILING:
                # towards inf.
                # if round_bit: x += 1; trunc(x)
                addOneFlag = round_bit
            elif rounding == HFloatTmpRounding.ROUND_FLOOR:
                addOneFlag = b0
            else:
                raise  AssertionError("Unsupported rounding type", rounding)
            valueSliced = value[:-fracSizeDiff]

            if saturation == HFloatTmpSaturation.SATURATE_INF:
                valueRounded = incrSat(valueSliced._cast_sign(signed), addOneFlag)._cast_sign(None)
            elif saturation == HFloatTmpSaturation.SATURATE_NONE:
                valueRounded = addOneFlag._ternary(valueSliced + 1, valueSliced)
            else:
                raise NotImplementedError(saturation)

            inInt = valueRounded[:outTy.frac_bit_length]
            outFrac = valueRounded[outTy.frac_bit_length:] if hasFrac else None

    elif fracSizeDiff > 0:
        # lsb = value[0]
        # outFrac = Concat(inFrac, *(lsb for _ in range(fracSizeDiff)))
        outFrac = ConcatOptional(inFrac, HBits(fracSizeDiff).from_py(0)) if hasFrac else None
    else:
        outFrac = inFrac if hasFrac else None

    if inTy.int_bit_length == outTy.int_bit_length:
        if hasFrac:
            res = ConcatOptional(inInt, outFrac)
        else:
            res = inInt
    elif inTy.int_bit_length < outTy.int_bit_length:
        # extend
        outInt = inInt._ext(outTy.int_bit_length, signed)
        if hasFrac:
            res = ConcatOptional(outInt, outFrac)
        else:
            res = outInt
    else:
        outInt = inInt[outTy.int_bit_length:]
        if hasFrac:
            res = ConcatOptional(outInt, outFrac)
        else:
            res = outInt

        if saturation == HFloatTmpSaturation.SATURATE_INF:
            resTy = res._dtype
            newMsbBit = inInt[outTy.int_bit_length - 1]
            if signed:
                # overflow happens if all cut of top bits of rounded inInt are not MSB
                otherCutOffBits = inInt[:outTy.int_bit_length - 1]
                otherCutOffWidth = otherCutOffBits._dtype.bit_length()
                assert not otherCutOffBits._dtype.signed
                otherCutOffTy = otherCutOffBits._dtype.from_py
                overflow = newMsbBit._ternary(
                    otherCutOffTy(mask(otherCutOffWidth)),
                    otherCutOffTy(0)
                ) != otherCutOffBits
                saturatedValMin = mask(resTy.bit_length())  # min signed val
                saturatedValMax = mask(resTy.bit_length() - 1)  # max signed val

            else:
                # overflow is all cut of top bits of rounded inInt are not 0
                overflow = inInt[:outTy.int_bit_length] != 0
                saturatedValMin = 0
                saturatedValMax = mask(resTy.bit_length())

            saturatedVal = newMsbBit._ternary(
                    resTy.from_py(saturatedValMin),
                    resTy.from_py(saturatedValMax),
            )

            res = overflow._ternary(
                saturatedVal,
                res,
            )

        elif saturation == HFloatTmpSaturation.SATURATE_NONE:
            pass
        else:
            raise NotImplementedError(saturation)

    assert res._dtype.bit_length() == outTy.bit_length(), (res._dtype, outTy)
    return res

# def fixp_resize_inHlsNetlist(inTy: HFixedPointQ,
#          outTy: HFixedPointQ,
#          value: HlsNetNodeOut,
#          roundingOverride=None,
#          saturationOverride=None,
#          worklist=None) -> HlsNetNodeOut:
#   """
#   :note: same functionality as fixp_resize, but for HlsNetlist
#   """
#   signed = inTy.signed
#   assert signed == outTy.signed, (inTy, outTy)
#   if inTy == outTy:
#       return value
#
#   builder: HlsNetlistBuilder = value.obj.getHlsNetlistBuilder()
#   and_ = builder.buildAnd
#   not_ = builder.buildNot
#   defaultHigh = lambda high, dtype: high if high is not None else dtype.bit_length()
#   slice_ = lambda v, high, low: builder.buildIndexConstSlice(HBits(defaultHigh(high, v._dtype) - low), v, defaultHigh(high, v._dtype), low, worklist)
#   index_ = lambda v, i: builder.buildIndexConst(BIT, v, i)
#   getMsb = builder.buildGetMsb
#   concat = builder.buildConcat
#
#   rounding = roundingOverride if roundingOverride is not None else inTy.rounding
#   saturation = saturationOverride if saturationOverride is not None else inTy.saturation
#   inInt = slice_(value, inTy.int_bit_length + inTy.frac_bit_length, inTy.frac_bit_length, 0)
#   inFrac = slice_(value, inTy.frac_bit_length, 0)
#   fracSizeDiff = outTy.frac_bit_length - inTy.frac_bit_length
#   if fracSizeDiff < 0:
#       # output fraction part is smaller, need truncation and rounding
#       hasFrac = bool(outTy.frac_bit_length)
#
#       if rounding == HFloatTmpRounding.ROUND_FLOOR or (rounding == HFloatTmpRounding.ROUND_DOWN and not signed):
#           # just truncation
#           if hasFrac:
#               outFrac = slice_(inFrac, None, -fracSizeDiff)
#           else:
#               outFrac = None
#       else:
#           round_bit = index_(inFrac, -fracSizeDiff - 1 - 1)  # most significant removed bit
#           if rounding == HFloatTmpRounding.ROUND_HALF_EVEN:
#               # nearest with ties going to nearest even integer. (c default)
#               # if round_bit && newLsb: x += 1; trunc(x)
#               if hasFrac:
#                   outFracLsb = index_(inFrac, -fracSizeDiff)
#               else:
#                   outFracLsb = index_(inInt, 0)
#               addOneFlag = and_(round_bit, outFracLsb)
#           elif rounding == HFloatTmpRounding.ROUND_HALF_UP:
#               #  nearest with ties going away from 0.
#               # if round_bit && x > 0: x += 1; trunc(x)
#               addOneFlag = and_(round_bit, getMsb(inInt))
#           elif rounding == HFloatTmpRounding.ROUND_DOWN:
#               #  towards 0.
#               # if round_bit && x < 0: x += 1; trunc(x)
#               addOneFlag = and_(round_bit, not_(getMsb(inInt)))
#           elif rounding == HFloatTmpRounding.ROUND_CEILING:
#               # towards inf.
#               # if round_bit: x += 1; trunc(x)
#               addOneFlag = round_bit
#           else:
#               raise  AssertionError("Unsupported rounding type", rounding)
#
#           valueSliced = value[:-fracSizeDiff]
#
#           if saturation == HFloatTmpSaturation.SATURATE_INF:
#               valueRounded = builder.buildIncr(valueSliced, en=addOneFlag, saturateSigned=signed, saturateUnsigned=not signed)
#           elif saturation == HFloatTmpSaturation.SATURATE_NONE:
#               valueRounded = builder.buildIncr(valueSliced)
#           else:
#               raise NotImplementedError(saturation)
#
#           inInt = valueRounded[:outTy.frac_bit_length]
#           outFrac = valueRounded[outTy.frac_bit_length:]
#
#   elif fracSizeDiff > 0:
#       lsb = index_(value, 0)
#       outFrac = concat((lsb for _ in range(-fracSizeDiff)), inFrac)
#   else:
#       outFrac = inFrac
#
#   if inTy.int_bit_length == outTy.int_bit_length:
#       res = concat(outFrac, inInt)
#   elif inTy.int_bit_length < outTy.int_bit_length:
#       # extend
#       if signed:
#           outInt = builder.buildSExt(inInt)
#       else:
#           outInt = builder.buildZext(inInt)
#
#       res = Concat(outInt, outFrac)
#   else:
#       outInt = slice_(inInt, outTy.int_bit_length, 0)
#       res = concat(outFrac, outInt)
#       if saturation == HFloatTmpSaturation.SATURATE_INF:
#           resTy = res._dtype
#           if signed:
#               # overflow happens all cut of top bits of rounded inInt are not MSB
#               newMsbBit = index_(inInt, outTy.int_bit_length - 1)
#               otherCutOffBits = slice_(inInt, None, outTy.int_bit_length - 1)
#               otherCutOffWidth = otherCutOffBits._dtype.bit_length()
#               otherCutOffTy = otherCutOffBits._dtype._from_py
#               overflow = newMsbBit._ternary(
#                   otherCutOffTy(mask(otherCutOffWidth)),
#                   otherCutOffTy(0)
#               ) != otherCutOffBits
#               res = overflow._ternary(
#                   newMsbBit._ternary(
#                       resTy.from_py(mask(resTy.bit_length())),  # min signed val
#                       resTy.from_py(mask(resTy.bit_length() - 1)),  # max signed val
#                   ),
#                   res,
#               )
#
#           else:
#               # overflow is all cut of top bits of rounded inInt are not 0
#               overflow = inInt[:outTy.int_bit_length] != 0
#               res = overflow._ternary(
#                   resTy.from_py(mask(resTy.bit_length())),  # max value
#                   res,
#               )
#
#       elif saturation == HFloatTmpSaturation.SATURATE_NONE:
#           pass
#       else:
#           raise NotImplementedError(saturation)
#   return res
