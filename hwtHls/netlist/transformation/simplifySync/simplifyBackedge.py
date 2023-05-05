from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifyUtils import disconnectAllInputs
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.debugTracer import DebugTracer


def netlistReduceUnusedBackedgeBuffer(
        dbgTracer: DebugTracer,
        n: HlsNetNodeReadBackedge,
        worklist: UniqList[HlsNetNode],
        removed: Set[HlsNetNode]):
    """
    If read data and control is never used it means that this channel is unused at all and it is removed by this function.
    """
    for uses in n.usedBy:
        for _ in uses:
            # has some use and thus it is not removed
            return False

    with dbgTracer.scoped(netlistReduceUnusedBackedgeBuffer, n):
        dbgTracer.log("rm")
        w = n.associatedWrite
        # else remove read and also write and update reachDb appropriately
        # cut off this write and read from ordering
        for _n in (n, w):
            #reachDb.addAllDepsToOutUseChange(_n)
            #reachDb.addAllUsersToInDepChange(_n)
            #reachDb.popNode(_n)

            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, _n, worklist)
            # cut off all data
            disconnectAllInputs(_n, worklist)
            removed.add(_n)

        #reachDb.commitChanges()
