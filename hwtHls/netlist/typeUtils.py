from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.bits import HBits


def dtypeEqualSignIgnore(t0: HdlType, t1: HdlType):
    return t0 == t1 or (
        isinstance(t0, HBits) and 
        isinstance(t1, HBits) and
        t0.bit_length() == t1.bit_length()
    )


def dtypeEqualSignAprox(t0: HdlType, t1: HdlType):
    return t0 == t1 or (
        dtypeEqualSignIgnore(t0, t1) and
        bool(t0.signed) == bool(t1.signed)
    )
