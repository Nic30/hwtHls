from hwt.hdl.types.bits import Bits
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.vectorUtils import fitTo_t
from hwtHls.frontend.pyBytecode import hlsBytecode
from hwtHls.frontend.pyBytecode.markers import PyBytecodeInline
from pyMathBitPrecise.bit_utils import mask
from tests.bitOpt.countBits import countBits
from tests.floatingpoint.fptypes import IEEE754Fp


# based on:
# https://github.com/dawsonjon/fpu/blob/master/int_to_float/int_to_float.v
# https://github.com/hVHDL/hVHDL_floating_point/blob/main/float_to_integer_converter/float_to_integer_converter_pkg.vhd
@hlsBytecode
def IEEE754FpFromInt(a: RtlSignalBase[Bits], t: IEEE754Fp):
    intW = a._dtype.bit_length()
    res = t.from_py(None)
    exp_t = res.exponent._dtype
    # convert_0
    if a._eq(0):
        # we check for 0 because conversion alg. searches for
        # leading 1 and would end up in infinite cycle if 0 was on input
        res.sign = res.sign._dtype.from_py(0)
        res.mantissa = res.mantissa._dtype.from_py(0)
        res.exponent = exp_t.from_py(0)
    else:
        res.sign = a[intW - 1]
        if a._dtype.signed:
            res.exponent = exp_t.from_py(-t.EXPONENT_OFFSET + intW - 1)  # = intW - 1 converted to exponent format
            value = res.sign._ternary(-a, a)._unsigned()
        else:
            raise NotImplementedError(a._dtype, "implemented only for signed")
        # convert_1
        # shift value so it starts with 1 (to normalize number)
        leadingZeroCnt = PyBytecodeInline(countBits)(value, 0, True)
        for _leadingZeroCnt in range(0, intW + 1):
            # All shift values mut be checked because we need to generate hardware which works for every value
            # case with 0 is the default case with 0 shift
            # case with intW is  means that the value is 0 and no shift is required
            if leadingZeroCnt._eq(_leadingZeroCnt):
                break
            value <<= 1
        res.exponent -= fitTo_t(leadingZeroCnt, exp_t, shrink=False)
        # compute rounding
        cutOffWidth = intW - t.MANTISSA_WIDTH - 1  # how many lower bits to cut due to mantissa/input width difference
        # for 32b int and 32b float (mantissa width=23) this = 8
        mantissa = Bits(t.MANTISSA_WIDTH + 1).from_py(None)
        if cutOffWidth > 0:
            mantissa = value[:cutOffWidth]  # mantissa + MSB
            guard = value[cutOffWidth - 1]
            round_bit = value[cutOffWidth - 2]
            sticky_bit = value[cutOffWidth - 3:] != 0
            mantissaOverflow = guard & (round_bit | sticky_bit | res.mantissa[0])
            if mantissaOverflow:
                mantissaAll1 = mantissa._eq(mask(t.MANTISSA_WIDTH + 1))
                if mantissaAll1:
                    res.exponent += 1
                mantissa += 1
        else:
            mantissa = fitTo_t(value, mantissa._dtype)

        # pack
        res.mantissa = mantissa[t.MANTISSA_WIDTH:]

    return res
