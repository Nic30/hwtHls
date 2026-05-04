from copy import copy
from typing import Union, Self

from hwt.hdl.types.typeCast import toHVal
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from tests.math.fixp.fixpTypes import HFixedPointQComaptibleValue
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp
from tests.math.hFloatTmp.hFloatTmpOps import fmul, fadd, fcmp_oeq, fcmp_one, fcmp_olt, \
    fcmp_ogt, fcmp_oge, fcmp_ole, fsub, fdiv


class HFixedPointQRtlSignal(RtlSignal):

    def __add__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fadd(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))._explicit_cast(self._dtype)

    def __sub__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fsub(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))._explicit_cast(self._dtype)

    def __mul__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fmul(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))._explicit_cast(self._dtype)

    def __truediv__(self, other: HFixedPointQComaptibleValue):
        other = toHVal(other, HFloatTmp)
        return fdiv(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))._explicit_cast(self._dtype)

    def _eq(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_oeq(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __ne__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_one(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __lt__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_olt(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __gt__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_ogt(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __ge__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_oge(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified

    def __le__(self, other: HFixedPointQComaptibleValue) -> Union["HBitsConst", Self]:
        other = toHVal(other, HFloatTmp)
        try:
            return fcmp_ole(self._explicit_cast(HFloatTmp), other._explicit_cast(HFloatTmp))
        except Exception as e:
            # simplification of previous exception traceback
            e_simplified = copy(e)
            raise e_simplified
