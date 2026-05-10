from typing import Self, Optional

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import APFloat, APInt, Type, HFloatTmpConfig
from tests.math.fixp.fixpTypes import HFixedPointQ


class HFixedPointQConst(HConst):
    """
    :ivar val: raw bits of float value (represented as non-negative int in Python)
    :ivar vld_mask: raw bit mask for validity of val
    """

    @classmethod
    def from_py(cls, typeObj: HFixedPointQ, val: Optional[float], vld_mask=None) -> Self:
        if val is not None:
            cfg: HFloatTmpConfig = typeObj.getHFloatTmpConfig()
            v = cfg.bitCastAPFloatToHFloatTmpAPInt(APFloat(float(val)))
            v = int(v)
            v &= typeObj.all_mask()
        else:
            v = 0

        if vld_mask is None:
            vld_mask = typeObj.all_mask()
        else:
            vld_mask &= typeObj.all_mask()
        return cls(typeObj, v, vld_mask=vld_mask)

    def __float__(self):
        if self._is_full_valid():
            cfg:HFloatTmpConfig = self._dtype.getHFloatTmpConfig()
            f = cfg.bitCastHFloatTmpAPIntToAPFloat(APInt(self._dtype.bit_length(), f"{self.val:x}", 16))
            return float(f)
        else:
            return None

    def toLlvm(self, toLlvm: "ToLlvmIrTranslator"):
        t = Type.getIntNTy(toLlvm.ctx, self._dtype.bit_length())
        return toLlvm._translateExprInt(self.val, t)

    def to_py(self) -> Optional[float]:
        if self._is_full_valid():
            return float(self)
        else:
            return None

    def __repr__(self) -> str:
        if self._is_full_valid():
            vld_mask = ""
        else:
            vld_mask = ", mask {0:x}".format(self.vld_mask)
        return "<{0:s} {1:s}({2:f}){3:s}>".format(
            self.__class__.__name__, repr(self.val), float(self), vld_mask)
