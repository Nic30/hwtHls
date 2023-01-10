from typing import Generator

from hwt.doc_markers import internal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class _HOrderingVoidT(HdlType):

    def bit_length(self):
        return 0

    @internal
    @classmethod
    def getValueCls(cls):
        try:
            return cls._valCls
        except AttributeError:
            cls._valCls = _VoidValue
            return cls._valCls


class _VoidValue(HValue):
    
    @classmethod
    def from_py(cls, typeObj, val, vld_mask=None):
        assert val is None, ("Only allowed value is None because void value does not contain any data", val)
        return cls(typeObj, None, vld_mask=None)

    def __repr__(self):
        return f"<void>"

class _HExternalDataDepT(_HOrderingVoidT):
    pass

"""
:var HOrderingVoidT: A type used for connections between HlsNetNode instances to keep its ordering during scheduling.
    (similar to glue type in LLVM)
:var HExternalDataDepT: Same as a HOrderingVoidT but in addition it means that there is an external data connection
    on outside of this component which asserts that connected two nodes are asserted to have ordering by externally connected circuit.
"""
HOrderingVoidT = _HOrderingVoidT()
HExternalDataDepT = _HExternalDataDepT()


def HdlType_isNonData(t: HdlType):
    return t is HOrderingVoidT or t is HExternalDataDepT 


class HlsNetNodeOrderable(HlsNetNode):
    
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        raise NotImplementedError(
            "Override this method in derived class", self)

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        raise NotImplementedError(
            "Override this method in derived class", self)
