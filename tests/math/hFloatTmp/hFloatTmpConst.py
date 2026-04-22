import math
from operator import add, sub, mul, truediv, lt, le, gt, ge, eq, ne, pow
from typing import Self, Union, Optional, Callable

from hwt.hdl.const import HConst
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.bitsRtlSignal import HBitsRtlSignal
from hwt.hdl.types.defs import BIT
from hwt.mainBases import RtlSignalBase
from hwtHls.llvm.llvmIr import Type, ConstantFP
from pyMathBitPrecise.bit_utils import ValidityError
from tests.math.hFloatTmp.hFloatTmpOps import fadd, fsub, fmul, \
    fdiv, fpowi, fcmp_olt, fcmp_ole, fcmp_oeq, fcmp_one, fcmp_ogt, fcmp_oge, \
    fpow, fround, fmod, fabs

_HFloatTmpValue = Union["HFloatTmpConst", "HFloatTmpRtlSignal"]


class HFloatTmpConst(HConst):

    @classmethod
    def from_py(cls, typeObj: "HFloatTmp", val: Union[float, int, None],
                vld_mask: Optional[int]=None) -> Self:
        if val is None:
            val = math.nan
            if vld_mask is None:
                vld_mask = 0
        else:
            val = float(val)
            if vld_mask is None:
                vld_mask = typeObj.all_mask()
            elif vld_mask == 0:
                val = math.nan
            else:
                if vld_mask != typeObj.all_mask():
                    raise NotImplementedError(val, vld_mask)

        # convert float to raw bytes store in as an integer
        # val = int.from_bytes(struct.pack("d", val), byteorder='little')
        return cls(typeObj, val, vld_mask=vld_mask)

    def __hash__(self) -> int:
        return hash((self._dtype, self.val, self.vld_mask))

    def __float__(self) -> float:
        self.val: float
        if self.vld_mask != self._dtype.all_mask():
            raise ValidityError()
        return self.val
        # return struct.unpack("d", self.val.to_bytes(8, byteorder='little'))[0]

    def __int__(self) -> int:
        return int(float(self))

    def _applyBinFnForConstants(self, other: Union[float, Self],
                                fn: Callable[[float, float], float],
                                opFn: Callable[[Self, "HFloatTmpRtlSignal"], RtlSignalBase]) -> _HFloatTmpValue:
        """
        :param fn: function which will evaluate operator with specified operands in python
        :param opFn: function which will construct hw conversible operator and its result RtlSignal
        """
        vld_mask = self.vld_mask
        if isinstance(other, self.__class__):
            vld_mask &= other.vld_mask
            other = other.val
        elif isinstance(other, (float, int)):
            other = other
        elif isinstance(other, RtlSignalBase):
            return opFn(self, other)
        else:
            raise NotImplementedError(self, fn, other)
        res = fn(self.val, other)
        assert isinstance(res, float), res
        return self.__class__(self._dtype, res, vld_mask)

    def _applyRBinFnForConstants(self, other: Union[float, Self],
                                fn: Callable[[float, float], float],
                                opFn: Callable[["HFloatTmpRtlSignal", Self], RtlSignalBase]) -> _HFloatTmpValue:
        """
        :note: same as :meth:`~._applyBinFnForConstants` just self is LHS and other is RHS
        """
        vld_mask = self.vld_mask
        if isinstance(other, self.__class__):
            vld_mask &= other.vld_mask
            other = other.val
        elif isinstance(other, (float, int)):
            other = other
        elif isinstance(other, RtlSignalBase):
            return opFn(other, self)
        elif isinstance(other, HBitsConst):
            if other._is_full_valid():
                other = float(int(other))
            else:
                other = 0.0
                vld_mask = 0
        else:
            raise NotImplementedError(other)

        res = fn(other, self.val)
        assert isinstance(res, float), res
        return self.__class__(self._dtype, res, vld_mask)

    def _applyCmpFnForConstants(self, other: Union[float, Self],
                                 fn: Callable[[float, float], bool],
                                 opFn: Callable[[Self, RtlSignalBase], HBitsRtlSignal]) -> Union[HBitsConst, HBitsRtlSignal]:
        """
        :note: for param doc see :meth:`~._applyBinFnForConstants`
        """
        vld_mask = self.vld_mask
        if isinstance(other, self.__class__):
            vld_mask &= other.vld_mask
            other = other.val
        elif isinstance(other, float):
            other = other
        elif isinstance(other, int):
            other = float(other)
        elif isinstance(other, RtlSignalBase):
            return opFn(self, other)
        else:
            raise NotImplementedError(other)
        return BIT._from_py(fn(self.val, other), int(vld_mask == self._dtype.all_mask()))

    def _applyRCmpFnForConstants(self, other: Union[float, Self],
                                 fn: Callable[[float, float], bool],
                                 opFn: Callable[[RtlSignalBase, Self], HBitsRtlSignal]) -> Union[HBitsConst, HBitsRtlSignal]:
        """
        :note: same as :meth:`~._applyCmpFnForConstants` just self is LHS and other is RHS
        """
        vld_mask = self.vld_mask
        if isinstance(other, self.__class__):
            vld_mask &= other.vld_mask
            other = other.val
        elif isinstance(other, float):
            other = other
        elif isinstance(other, int):
            other = float(other)
        elif isinstance(other, RtlSignalBase):
            return opFn(other, self)
        else:
            raise NotImplementedError(other)
        return BIT._from_py(fn(other, self.val), int(vld_mask == self._dtype.all_mask()))

    def __add__(self, other: Union[float, Self]) -> Self:
        return self._applyBinFnForConstants(other, add, fadd)

    def __radd__(self, other: Union[float, Self]) -> Self:
        return self._applyRBinFnForConstants(other, add, fadd)

    def __sub__(self, other: Union[float, Self]) -> Self:
        return self._applyBinFnForConstants(other, sub, fsub)

    def __rsub__(self, other: Union[float, Self]) -> Self:
        return self._applyRBinFnForConstants(other, sub, fsub)

    def __mul__(self, other: Union[float, Self]) -> Self:
        return self._applyBinFnForConstants(other, mul, fmul)

    def __rmul__(self, other: Union[float, Self]) -> Self:
        return self._applyRBinFnForConstants(other, mul, fmul)

    def __truediv__(self, other: Union[float, Self]) -> Self:
        return self._applyBinFnForConstants(other, truediv, fdiv)

    def __rtruediv__(self, other: Union[float, Self]) -> Self:
        return self._applyRBinFnForConstants(other, truediv, fdiv)

    def __mod__(self, other: Union[float, Self]) -> Self:
        return self._applyBinFnForConstants(other, math.fmod, fmod)

    def __rmod__(self, other: Union[float, Self]) -> Self:
        return self._applyRBinFnForConstants(other, math.fmod, fmod)

    def __neg__(self) -> Self:
        return self.__class__(self._dtype, -self.val, self.vld_mask)

    def __lt__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyCmpFnForConstants(other, lt, fcmp_olt)

    def __rlt__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyRCmpFnForConstants(other, lt, fcmp_olt)

    def __le__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyCmpFnForConstants(other, le, fcmp_ole)

    def __rle__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyRCmpFnForConstants(other, le, fcmp_ole)

    def __eq__(self, other: Union[float, Self]) -> HBitsConst:
        try:
            if isinstance(other, (int, float)):
                return float(self) == other
            if isinstance(other, HFloatTmpConst):
                return float(self) == float(other)
        except ValidityError:
            return False
        return False

    def _eq(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyCmpFnForConstants(other, eq, fcmp_oeq)

    def __req__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyRCmpFnForConstants(other, eq, fcmp_oeq)

    def __ne__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyCmpFnForConstants(other, ne, fcmp_one)

    def __rne__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyRCmpFnForConstants(other, ne, fcmp_one)

    def __ge__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyCmpFnForConstants(other, ge, fcmp_oge)

    def __rge__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyRCmpFnForConstants(other, ge, fcmp_oge)

    def __gt__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyCmpFnForConstants(other, gt, fcmp_ogt)

    def __rgt__(self, other: Union[float, Self]) -> HBitsConst:
        return self._applyRCmpFnForConstants(other, gt, fcmp_ogt)

    def __pow__(self, other: Union[float, Self]) -> Self:
        if isinstance(other, HBitsConst):
            if other._is_full_valid():
                other = int(other)
            else:
                return self.__class__(self._dtype, 0.0, 0)
        elif isinstance(other, HBitsRtlSignal):
            return fpowi(self, other)
        elif isinstance(other, RtlSignalBase) and other._dtype == self._dtype:
            return fpow(self, other)

        return self._applyBinFnForConstants(other, pow, pow)

    def __abs__(self):
        return fabs(self)

    def __round__(self):
        return fround(self)

    def toLlvm(self, toLlvm: "ToLlvmIrTranslator"):
        t = Type.getDoubleTy(toLlvm.ctx)
        return ConstantFP.get(t, self.val)

    def __repr__(self):
        if self._is_full_valid():
            m = ""
            v = float(self)
        else:
            m = ", mask {0:x}".format(self.vld_mask)
            v = self.val

        return "<{0:s} {1:f}{2:s}>".format(
            self.__class__.__name__, v, m)
