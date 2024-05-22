from typing import Tuple

from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.node import HlsNetNode
from hwt.pyUtils.typingFuture import override


class HlsNetNodeIoClusterCore(HlsNetNode):
    """
    This node is connected only to HlsNetNodeExplicitSync instances.
    It represents a cluster of IO operations which do present a circuit between these IO operations.
    The reason why is this an explicit node is to avoid complicated queries for IO operation relations
    while transforming the circuit.
    
    :note: Connected nodes may be inputs and outputs at once. If this is the case the node is connected as output. 
    :note: inputs are always of HVoidOrdering type
    """

    def __init__(self, netlist:HlsNetlistCtx, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.inputNodePort = self._addOutput(HVoidOrdering, "inputNodePort")
        self.outputNodePort = self._addOutput(HVoidOrdering, "outputNodePort")

    def clone(self, memo:dict, keepTopPortsConnected: bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNode.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.inputNodePort = y._outputs[self.inputNodePort.out_i]
            y.outputNodePort = y._outputs[self.outputNodePort.out_i]
        return y, isNew

    @override
    def _removeOutput(self, index: int):
        raise NotImplementedError()

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated, self
        self._isRtlAllocated = True
        return []
        # raise AssertionError("This is a temporary node which is not intended for instantiation")

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self._id:d}>"
