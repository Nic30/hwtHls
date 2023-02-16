from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HVoidOrdering
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION


class HlsNetNodeIoClusterCore(HlsNetNode):
    """
    This node is connected only to HlsNetNodeExplicitSync instances.
    It represents a cluster of IO operations which do present a circuit between these IO operations.
    The reason why is this an explicit node is to avoid complicated queries for IO operation relations
    while transforming the circuit.
    
    :note: Connected nodes may be inputs and outputs at once. If this is the case the node is connected as output. 
    :note: inputs are always of HVoidOrdering type
    """
    
    def __init__(self, netlist:"HlsNetlistCtx", name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self.inputNodePort = self._addOutput(HVoidOrdering, "inputNodePort")
        self.outputNodePort = self._addOutput(HVoidOrdering, "outputNodePort")

    def _removeOutput(self, i:int):
        raise NotImplementedError()

    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        return []
        # raise AssertionError("This is a temporary node which is not intended for instantiation") 

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__:s} {self._id}>"
