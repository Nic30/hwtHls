from hwt.hObjList import HObjList
from hwt.hdl.types.bits import HBits
from hwtHls.llvm.llvmIr import Value
from tests.math.hFloatTmp.hFloatTmp import HFloatTmp


def HObjList_getHdlType(vVal):
    if isinstance(vVal, Value):
        _t = vVal.getType()
        if _t.isDoubleTy():
            return HFloatTmp
        else:
            return HBits(_t.getScalarSizeInBits())
    elif isinstance(vVal, (HObjList, tuple)):
        return HObjList_getHdlType(vVal[0])[len(vVal)]
    else:
        return getattr(vVal, "_dtypeOrig", vVal._dtype)
