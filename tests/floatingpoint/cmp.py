from hwt.hdl.types.bits import Bits
from hwt.hdl.value import HValue
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwtHls.frontend.pyBytecode import hlsBytecode
from tests.floatingpoint.fptypes import IEEE754Fp


bit2_t = Bits(2)


class IEEE754FpCmpResult():
    EQ = bit2_t.from_py(0b00)
    LT = bit2_t.from_py(0b01)
    GT = bit2_t.from_py(0b10)
    UNKNOWN = bit2_t.from_py(0b11)  # for operations with NaN

    @classmethod
    def toStr(cls, val: HValue[bit2_t]):
        if not val._is_full_valid():
            return "INVALID"
        if val == cls.EQ:
            return "EQ"
        elif val == cls.LT:
            return "LT"
        elif val == cls.GT:
            return "GT"
        else:
            assert val == cls.UNKNOWN, val
            return "UNKNOWN"


# https://stackoverflow.com/questions/1565164/what-is-the-rationale-for-all-comparisons-returning-false-for-ieee754-nan-values
@hlsBytecode
def IEEE754FpCmp(a: RtlSignalBase[IEEE754Fp], b: RtlSignalBase[IEEE754Fp]):
    """
    :note: expects normalized numbers
    """
    res = bit2_t.from_py(None)
    t:IEEE754Fp = a._dtype
    if t.isNaN(a) | t.isNaN(b):
        # if any operand is NaN the result is unknown
        res = IEEE754FpCmpResult.UNKNOWN
    elif ~a.sign & ~b.sign:
        # both sign bits are same so we have to compare with exponent bits then after mantissa bits
        # only special value there can be only +inf and they will end up in EQ case so no special check needed
        if a.exponent > b.exponent:
            res = IEEE754FpCmpResult.GT
        elif a.exponent < b.exponent:
            res = IEEE754FpCmpResult.LT
        elif a.mantissa > b.mantissa:
            res = IEEE754FpCmpResult.GT
        elif a.mantissa < b.mantissa:
            res = IEEE754FpCmpResult.LT
        else:
            res = IEEE754FpCmpResult.EQ
    elif a.sign & b.sign:
        # same as previous case just reversed because because now we have negative numbers
        if a.exponent > b.exponent:
            res = IEEE754FpCmpResult.LT
        elif a.exponent < b.exponent:
            res = IEEE754FpCmpResult.GT
        elif a.mantissa > b.mantissa:
            res = IEEE754FpCmpResult.LT
        elif a.mantissa < b.mantissa:
            res = IEEE754FpCmpResult.GT
        else:
            res = IEEE754FpCmpResult.EQ
    elif b.sign:
        # if b.sign=1 then a is positive number and b is negative number so a>b
        res = IEEE754FpCmpResult.GT
    else:
        res = IEEE754FpCmpResult.LT
    return res
