import math
from typing import Self, Union, Optional

from hwt.hdl.const import HConst
from hwtHls.llvm.llvmIr import Type, ConstantFP
from pyMathBitPrecise.bit_utils import ValidityError


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

    def __float__(self):
        self.val: float
        if self.vld_mask != self._dtype.all_mask():
            raise ValidityError()
        return self.val
        # return struct.unpack("d", self.val.to_bytes(8, byteorder='little'))[0]

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
