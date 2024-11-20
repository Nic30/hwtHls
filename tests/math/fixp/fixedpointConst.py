from typing import Self, Optional

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import HFloatTmpConfig, APFloat
from hwtHls.llvm.llvmIr import Type
from tests.math.fixp.fixedpoint import HFixedPointQ


class HFixedPointQConst(HConst):

    @classmethod
    def from_py(cls, typeObj: HFixedPointQ, val: Optional[float], vld_mask=None) -> Self:
        if val is not None:
            exponentOrIntWidth = typeObj.int_bit_length
            mantissaOrFracWidth = typeObj.frac_bit_length
            isInQFromat = True
            supportSubnormal = False
            hasSign = bool(typeObj.signed)
            hasIsNaN = False
            hasIsInf = False
            hasIs1 = False
            hasIs0 = False

            cfg = HFloatTmpConfig(
                exponentOrIntWidth,
                mantissaOrFracWidth,
                isInQFromat,
                supportSubnormal,
                hasSign,
                hasIsNaN,
                hasIsInf,
                hasIs1,
                hasIs0,
            )
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

    def toLlvm(self, toLlvm: "ToLlvmIrTranslator"):
        t = Type.getIntNTy(toLlvm.ctx, self._dtype.bit_length())
        return toLlvm._translateExprInt(self.val, t)

