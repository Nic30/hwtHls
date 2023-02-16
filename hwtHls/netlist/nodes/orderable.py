from typing import Generator

from hwt.doc_markers import internal
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.value import HValue
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class _HVoidOrdering(HdlType):
    """
    :note: use HVoidOrdering directly
    """

    def bit_length(self):
        return 0

    @internal
    @classmethod
    def getValueCls(cls):
        try:
            return cls._valCls
        except AttributeError:
            cls._valCls = _HVoidValue
            return cls._valCls


class _HVoidValue(HValue):
    
    @classmethod
    def from_py(cls, typeObj, val, vld_mask=None):
        assert val is None, ("Only allowed value is None because void value does not contain any data", val)
        return cls(typeObj, None, vld_mask=None)

    def __repr__(self):
        return f"<void>"


class _HVoidData(_HVoidOrdering):
    """
    :note: use HDataVoid directly
    """
    pass


class _HVoidExternData(_HVoidOrdering):
    """
    :note: use HVoidExternData directly
    """
    pass

"""
:var ~.HVoidOrdering: A type used for connections between HlsNetNode instances to keep its ordering during scheduling.
    (similar to glue type in LLVM)
:var ~.HVoidDataT: Same as HVoidOrdering but in addition it means that there is/was some data dependency.
:var ~.HVoidExternData: Same as a HVoidOrdering but in addition it means that there is an external data connection
    on outside of this component which asserts that connected two nodes are asserted to have ordering by externally connected circuit.
"""
HVoidOrdering = _HVoidOrdering()
HVoidData = _HVoidData()
HVoidExternData = _HVoidExternData()


def HdlType_isNonData(t: HdlType):
    return t is HVoidOrdering or t is HVoidExternData 


def HdlType_isVoid(t: HdlType):
    return t is HVoidOrdering or t is HVoidData or t is HVoidExternData 
    

class HlsNetNodeOrderable(HlsNetNode):
    
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        """
        Iterate input ports which are used for ordering between HlsNetNodeOrderable instances
        """
        raise NotImplementedError(
            "Override this method in derived class", self)
        
    def getOrderingOutPort(self) -> HlsNetNodeOut:
        """
        Get output port used for ordering between HlsNetNodeOrderable instances.
        """
        raise NotImplementedError(
            "Override this method in derived class", self)
