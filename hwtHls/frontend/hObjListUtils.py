from hwt.hwIOs.hwIOArray import HwIOArray


def HwIOArray_getHdlType(vVal):
    if isinstance(vVal, HwIOArray):
        return HwIOArray_getHdlType(vVal[0])[len(vVal)]
    else:
        return getattr(vVal, "_dtypeOrig", vVal._dtype)
