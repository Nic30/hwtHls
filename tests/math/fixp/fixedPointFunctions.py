from typing import Union

from hwt.code import Concat
from hwt.doc_markers import hwt_expr_producer
from hwtHls.code import incrSat, sext, zext
from pyMathBitPrecise.bit_utils import mask
from tests.math.fixp.fixedpoint import HFixedPointQ, ROUND_FLOOR, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_CEILING, SATURATE_INF, SATURATE_NONE


# add/sub is same as for int
@hwt_expr_producer
def resize(self,
           value: Union["HFixedPointQRtlSignal", "HFixedPointQConst"],
           outTy: HFixedPointQ,
           roundingOverride=None,
           saturationOverride=None) -> Union["HFixedPointQRtlSignal", "HFixedPointQConst"]:
    # https://github.com/WangXuan95/FPGA-FixedPoint/blob/master/RTL/fixedpoint.v#L22
    signed = self.signed
    assert signed == outTy.signed, (self, outTy)
    if self == outTy:
        return value

    rounding = roundingOverride if roundingOverride is not None else self.roundig
    saturation = saturationOverride if saturationOverride is not None else self.saturation

    inInt = value[:self.frac_bit_length]

    inFrac = value[self.frac_bit_length:]
    fracSizeDiff = outTy.frac_bit_length - self.frac_bit_length
    if fracSizeDiff < 0:
        # output fraction part is smaller, need truncation and rounding
        hasFrac = bool(outTy.frac_bit_length)
        outFrac = inFrac[:-fracSizeDiff] if hasFrac else None
        if rounding == ROUND_FLOOR or (rounding == ROUND_DOWN and not signed):
            pass  # just truncation
        else:
            round_bit = inFrac[:-fracSizeDiff - 1]  # most significant removed bit
            if rounding == ROUND_HALF_EVEN:
                # nearest with ties going to nearest even integer. (c default)
                # if round_bit && newLsb: x += 1; trunc(x)
                addOneFlag = round_bit & (outFrac[0] if hasFrac else inInt[0])
            elif rounding == ROUND_HALF_UP:
                #  nearest with ties going away from 0.
                # if round_bit && x > 0: x += 1; trunc(x)
                addOneFlag = round_bit & ~inInt[inInt._dtype.bit_length() - 1]
            elif rounding == ROUND_DOWN:
                #  towards 0.
                # if round_bit && x < 0: x += 1; trunc(x)
                addOneFlag = round_bit & ~inInt[inInt._dtype.bit_length() - 1]
            elif rounding == ROUND_CEILING:
                # towards inf.
                # if round_bit: x += 1; trunc(x)
                addOneFlag = round_bit
            else:
                raise  AssertionError("Unsupported rounding type", rounding)
            valueSliced = value[:-fracSizeDiff]

            if saturation == SATURATE_INF:
                valueRounded = incrSat(valueSliced, addOneFlag)
            elif saturation == SATURATE_NONE:
                valueRounded = valueSliced + 1
            else:
                raise NotImplementedError(saturation)

            inInt = valueRounded[:outTy.frac_bit_length]
            outFrac = valueRounded[outTy.frac_bit_length:]

    elif fracSizeDiff > 0:
        lsb = inFrac[0]
        outFrac = Concat(inFrac, (lsb for _ in range(-fracSizeDiff)))
    else:
        outFrac = inFrac

    if self.int_bit_length == outTy.int_bit_length:
        res = Concat(inInt, outFrac)
    elif self.int_bit_length < outTy.int_bit_length:
        # extend
        if signed:
            outInt = sext(inInt)
        else:
            outInt = zext(inInt)

        res = Concat(outInt, outFrac)
    else:
        outInt = inInt[outTy.int_bit_length:]
        res = Concat(outInt, outFrac)
        if saturation == SATURATE_INF:
            resTy = res._dtype
            if signed:
                # overflow is all cut of top bits of rounded inInt are not MSB
                newMsbBit = inInt[outTy.int_bit_length - 1]
                otherCutOffBits = inInt[:outTy.int_bit_length - 1]
                otherCutOffWidth = otherCutOffBits._dtype.bit_length()
                otherCutOffTy = otherCutOffBits._dtype._from_py
                overflow = newMsbBit._ternary(
                    otherCutOffTy(mask(otherCutOffWidth)),
                    otherCutOffTy(0)
                ) != otherCutOffBits
                res = overflow._ternary(
                    newMsbBit._ternary(
                        resTy.from_py(mask(resTy.bit_length())),  # min signed val
                        resTy.from_py(mask(resTy.bit_length() - 1)),  # max signed val
                    ),
                    res,
                )

            else:
                # overflow is all cut of top bits of rounded inInt are not 0
                overflow = inInt[:outTy.int_bit_length] != 0
                res = overflow._ternary(
                    resTy.from_py(mask(resTy.bit_length())),  # max value
                    res,
                )

        elif saturation == SATURATE_NONE:
            pass
        else:
            raise NotImplementedError(saturation)

    res = res._reinterpret_cast(outTy)
    return res

# multiplication produces twice the bits, (on bout sides, Q4.4 * Q4.4 = Q8.8, truncatable by taking middle bits)
# https://projectf.io/posts/fixed-point-numbers-in-verilog/
