from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.debugTracer import DebugTracer


def netlistReduceUnusedBackwardEdgeBuffer(
        dbgTracer: DebugTracer,
        n: HlsNetNodeReadBackwardEdge,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode]):
    """
    If read data and control is never used it means that this channel is unused at all and it is removed by this function.
    """
    for uses in n.usedBy:
        for _ in uses:
            # has some use and thus it is not removed
            return False

    with dbgTracer.scoped(netlistReduceUnusedBackwardEdgeBuffer, n):
        dbgTracer.log("rm")
        w = n.associated_write
        # else remove read and also write and update syncDeps appropriately
        # cut off this write and read from ordering
        for _n in (n, w):
            #syncDeps.addAllDepsToOutUseChange(_n)
            #syncDeps.addAllUsersToInDepChange(_n)
            #syncDeps.popNode(_n)
    
            netlistExplicitSyncDisconnectFromOrderingChain(_n)
            # cut off all data
            disconnectAllInputs(_n, worklist)
            removed.add(_n)
    
        #syncDeps.commitChanges()
