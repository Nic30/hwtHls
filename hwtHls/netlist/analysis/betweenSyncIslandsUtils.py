from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode


class BetweenSyncIsland():
    """
    An island of nodes between HlsNetNodeExplicitSync nodes (HlsNetNodeRead and HlsNetNodeWrite are subclasses)
    
    :note: inputs/outputs are not related to a read/write operations, it is related how node is positioned relatively to this cluster. 

    Specific cases of input output relations:
    * inputs and outputs are not inside of nodes
    * nodes may be empty
    * island may not have inputs or outputs but must have at least one
    * each input is input only of a single island
    * each output is output of a single node
    * if input is also an output it means that the node is somewhere in the middle of the island
    """

    def __init__(self, inputs: UniqList[HlsNetNodeExplicitSync],
                 outputs: UniqList[HlsNetNodeExplicitSync],
                 nodes: UniqList[HlsNetNode]):
        self.inputs = inputs
        self.nodes = nodes
        self.outputs = outputs
    
    def iterAllNodes(self):
        yield from self.inputs
        yield from self.nodes
        yield from self.outputs
    
    def __repr__(self):
        return (f"<{self.__class__.__name__:s} i={[n._id for n in self.inputs]} "
                f"o={[n._id for n in self.outputs]} "
                f"nodeCnt={len(self.nodes)}>")


def BetweenSyncIsland_getScheduledClkTimes(isl: BetweenSyncIsland, normalizedClkPeriod: int):
    clks = set()
    for n in isl.iterAllNodes():
        n: HlsNetNode
        clks.add(n.scheduledZero // normalizedClkPeriod)
    return clks
