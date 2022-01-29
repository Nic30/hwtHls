from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.types.bits import Bits


def dtypeEqualSignIgnore(t0: HdlType, t1: HdlType):
    return t0 == t1 or (
        isinstance(t0, Bits) and 
        isinstance(t1, Bits) and
        t0.bit_length() == t1.bit_length()
    )


def dtypeEqualSignAprox(t0: HdlType, t1: HdlType):
    return t0 == t1 or (
        dtypeEqualSignIgnore(t0, t1) and
        bool(t0.signed) == bool(t1.signed)
    )
