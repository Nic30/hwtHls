from typing import Generator

from hwt.hdl.types.hdlType import HdlType
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn


class _HOrderingVoidT(HdlType):

    def bit_length(self):
        return 0


class _HExternalDataDepT(_HOrderingVoidT):
    pass

"""
:var HOrderingVoidT: A type used for connections between HlsNetNode instances to keep its ordering during scheduling.
    (similar to glue type in LLVM)
:var HExternalDataDepT: Same as a HOrderingVoidT but in addition it means that there is an external data connection
    on outside of this component.
"""
HOrderingVoidT = _HOrderingVoidT()
HExternalDataDepT = _HExternalDataDepT()


class HlsNetNodeOrderable(HlsNetNode):
    
    def iterOrderingInputs(self) -> Generator[HlsNetNodeIn, None, None]:
        raise NotImplementedError(
            "Override this method in derived class", self)

    def getOrderingOutPort(self) -> HlsNetNodeOut:
        raise NotImplementedError(
            "Override this method in derived class", self)
