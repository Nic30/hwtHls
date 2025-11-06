from hwt.hwIOs.hwIOArray import HwIOArray
from hwtHls.llvm.llvmIr import Value


def HwIOArray_getHdlType(vVal):
    if isinstance(vVal, HwIOArray):
        return HwIOArray_getHdlType(vVal[0])[len(vVal)]
    else:
        return getattr(vVal, "_dtypeOrig", vVal._dtype)
