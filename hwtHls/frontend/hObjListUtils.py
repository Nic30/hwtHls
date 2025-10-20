from hwt.hdl.types.bits import HBits
from hwt.hwIOs.hwIOArray import HwIOArray
from hwtHls.llvm.llvmIr import Value
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


def HwIOArray_getHdlType(vVal):
    if isinstance(vVal, Value):
        _t = vVal.getType()
        if _t.isDoubleTy():
            return HFloatTmp
        else:
            return HBits(_t.getScalarSizeInBits())
    elif isinstance(vVal, HwIOArray):
        return HwIOArray_getHdlType(vVal[0])[len(vVal)]
    else:
        return getattr(vVal, "_dtypeOrig", vVal._dtype)
