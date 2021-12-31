from typing import List, Dict

from hwt.synthesizer.interface import Interface
from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage


class AllocatorArchitecturalElement():
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type
    """
    
    def __init__(self, allocator: "HlsAllocator"):
        self.allocator = allocator
        self.connections: List[ConnectionsOfStage] = []
        self.syncIn: Dict[float, Interface] = {}
        self.syncOut: Dict[float, Interface] = {}
