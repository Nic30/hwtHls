from typing import List, Set

from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn


class AllocatorArchitecturalElement():
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type
    """
    
    def __init__(self, allocator: "HlsAllocator"):
        self.allocator = allocator
        self.connections: List[ConnectionsOfStage] = []

    def _declareIo(self, node: HlsNetNode, allGroupNodes: Set[HlsNetNode]):
        """
        :meth:`~.declareIo` for a single node
        """
        for o, usedBy in zip(node._outputs, node.usedBy):
            for u in usedBy:
                u: HlsNetNodeIn
                if u.obj not in allGroupNodes:
                    o.obj.allocateRtlInstanceOutDeclr(self.allocator, o)
                    break

    def declareIo(self):
        """
        Declare all outputs which are used outside to allow instantiation of rest of the circuit.
        """
        raise NotImplementedError("Implement in child class")
    
    def allocateDataPath(self):
        """
        Allocate main RTL object which are required from HlsNetNode instances assigned to this element.
        """
        raise NotImplementedError("Implement in child class")
    
    def allocateSync(self):
        """
        Instantiate an additional RTL objects to implement the synchronization of the element
        which are not direclty present in input HlsNetNode instances.
        """
        raise NotImplementedError("Implement in child class")
    
