from copy import copy
from typing import Union, Self

from hwt.hdl.types.typeCast import toHVal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQComaptibleValue
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import fmul, fadd, fcmp_oeq, fcmp_one, fcmp_olt, \
    fcmp_ogt, fcmp_oge, fcmp_ole, fsub, fdiv, fround, fneg, fmod

_HFloatTmpValue = Union["HFloatTmpConst", "HFloatTmpRtlSignal"]


class HFloatTmpRtlSignal(RtlSignal):

    # def _applyBinFn(self, other: Union[float, Self],
    #                opFn: Callable[[Self, "HFloatTmpRtlSignal"], RtlSignalBase]) -> _HFloatTmpValue:
    #    """
    #    :param fn: function which will evaluate operator with specified operands in python
    #    :param opFn: function which will construct hw conversible operator and its result RtlSignal
    #    """
    #    if isinstance(other, float):
    #        other = HFloatTmp.from_py(other)
    #    res = opFn(self.val, other)
    #    return res

    def __add__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fadd(self, other)

    def __radd__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fadd(other, self)

    def __sub__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fsub(self, other)

    def __rsub__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fsub(other, self)

    def __mul__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fmul(self, other)

    def __rmul__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fmul(other, self)

    def __truediv__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fdiv(self, other)

    def __mod__(self, other: Union[float, Self]) -> Self:
        other = toHVal(other, HFloatTmp)
        return fmod(self, other)

    def __rmod__(self, other: Union[float, Self]) -> Self:
        other = toHVal(other, HFloatTmp)
        return fmod(other, self)

    def __neg__(self):
        return fneg(self)

    def _eq(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_oeq(self, other)
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __ne__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_one(self, other)
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __lt__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_olt(self, other)
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __gt__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_ogt(self, other)
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __ge__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_oge(self, other)
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __le__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_ole(self, other)
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __round__(self):
        return fround(self)
