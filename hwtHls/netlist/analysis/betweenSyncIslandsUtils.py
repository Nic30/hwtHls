from itertools import chain

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.schedulableNode import SchedTime


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

    def __init__(self, inputs: SetList[HlsNetNodeExplicitSync],
                 outputs: SetList[HlsNetNodeExplicitSync],
                 nodes: SetList[HlsNetNode]):
        self.inputs = inputs
        self.nodes = nodes
        self.outputs = outputs

    def substract(self, other: "BetweenSyncIsland"):
        assert self is not other
        self.inputs = SetList(i for i in self.inputs if i not in other.inputs)
        self.nodes = SetList(n for n in self.nodes if n not in other.nodes)
        self.outputs = SetList(o for o in self.outputs if o not in other.outputs)

    def iterAllNodes(self):
        yield from self.inputs
        yield from self.nodes
        yield from self.outputs

    def getScheduledClkTimes(self, normalizedClkPeriod: SchedTime):
        clks = set()
        for n in self.iterAllNodes():
            n: HlsNetNode
            clks.update(t // normalizedClkPeriod for t in chain(n.scheduledIn, n.scheduledOut, (n.scheduledZero,)))
        return clks

    def __repr__(self):
        return (f"<{self.__class__.__name__:s} i={[n._id for n in self.inputs]} "
                f"o={[n._id for n in self.outputs]} "
                f"nodeCnt={len(self.nodes)}>")

