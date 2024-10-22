from typing import Set

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifySync.reduceChannelGroup import netlistTryRemoveChannelGroup
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs


def netlistReduceUnusedBackedgeBuffer(
        dbgTracer: DebugTracer,
        n: HlsNetNodeReadBackedge,
        worklist: SetList[HlsNetNode]):
    """
    If read data and control is never used it means that this channel is unused at all and it is removed by this function.
    """
    for uses in n.usedBy:
        for _ in uses:
            # has some use and thus it is not removed
            return False

    w = n.associatedWrite
    g = w._loopChannelGroup
    isControlOfG = g is not None and g.getChannelUsedAsControl() is w
    if isControlOfG and not netlistTryRemoveChannelGroup(dbgTracer, g, worklist):
        # can not remove because it has control flow purpose
        return False

    with dbgTracer.scoped(netlistReduceUnusedBackedgeBuffer, n):
        # cut off this write and read from ordering
        for _n in (n, w):
            dbgTracer.log(("rm unused", _n._id))
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, _n, worklist)
            # cut off all data
            disconnectAllInputs(_n, worklist)
            _n.markAsRemoved()
        if g is not None and not isControlOfG:
            g.members.remove(w)

