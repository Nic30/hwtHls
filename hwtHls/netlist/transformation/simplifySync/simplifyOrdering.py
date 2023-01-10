from typing import Set, Sequence, Optional

from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, link_hls_nodes, \
    HlsNetNodeOut, unlink_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.orderable import HdlType_isNonData
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwt.pyUtils.uniqList import UniqList


def netlistExplicitSyncDisconnectFromOrderingChain(n: HlsNetNodeExplicitSync):
    for orderingI in n.iterOrderingInputs():
        netlistExplicitSyncOrderingBypass(n, orderingI)
    netlistExplicitSyncOrderingOutUsesDiscard(n)


def _explicitSyncAddUniqueOrdering(n: HlsNetNodeExplicitSync, newOrderingDeps: Sequence[HlsNetNodeOut], nOrderingUses: Optional[Set[HlsNetNodeExplicitSync]]):
    # collect already present ordering
    if nOrderingUses is None:
        nOrderingUses = set()
        for oi in n.iterOrderingInputs():
            nOrderingUses.add(n.dependsOn[oi.in_i].obj)

    # add dependencies from depObj to n
    for d in newOrderingDeps:
        if d.obj in nOrderingUses:
            # prevent ordering duplication
            continue
        else:
            nOrderingUses.add(d.obj)
            nOi = n._addInput("orderingIn")
            link_hls_nodes(d, nOi)

    return nOrderingUses


def netlistExplicitSyncOrderingBypass(orderingI: HlsNetNodeIn):
    """
    Used to cancel ordering connection for nodes which do have ordering guaranteed trough other means
    Distribute ordering dependencies from dependency of this input "dep" to all ordering user of this node "n"
    and forward ordering users of "n" ordering output port to "dep".
    
    .. code-block:: text
    
       --v 
        dep -> n  -> use

    to 
    .. code-block:: text
    
     ----+----+
         v    v 
        dep   n -> use
         |----------^    
    """
    n = orderingI.obj
    # rm orderingI of node n
    depOo = n.dependsOn[orderingI.in_i]
    depObj = depOo.obj
    
    depObj.usedBy[depOo.out_i].remove(orderingI)
    assert orderingI not in depObj.usedBy[depOo.out_i], (orderingI, "was multiple times in usedBy")
    n._removeInput(orderingI.in_i)
    
    _explicitSyncAddUniqueOrdering(n, (depObj.dependsOn[oi.in_i] for oi in depObj.iterOrderingInputs()), None)

    # add ordering uses from n to nodes with ordering dependency on n
    oo = n.getOrderingOutPort()
    depOrderingUses: Set[HlsNetNodeExplicitSync] = set()
    for u in depObj.usedBy[depOo.out_i]:
        depOrderingUses.add(u.obj)

    for u in n.usedBy[oo.out_i]:
        u: HlsNetNodeIn
        if u.obj in depOrderingUses:
            # prevent ordering duplication
            continue
        else:
            depOrderingUses.add(u.obj)
            i = u.obj._addInput("orderingIn")
            link_hls_nodes(depOo, i)


def netlistExplicitSyncOrderingOutUsesDiscard(n: HlsNetNodeExplicitSync):
    """
    Disconnect uses of ordering output of n and remove all ports which were originally connected.
    """
    o = n.getOrderingOutPort()
    for i in tuple(n.usedBy[o.out_i]):
        i: HlsNetNodeIn
        i.obj._removeInput(i.in_i)
    n.usedBy[o.out_i].clear()


def netlistTrivialOrderingReduce(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    modified = False
    for orderingI in tuple(n.iterOrderingInputs()):
        orderingI: HlsNetNodeIn
        dep = n.dependsOn[orderingI.in_i]
        if HdlType_isNonData(dep._dtype) and isinstance(dep.obj, HlsNetNodeConst):
            unlink_hls_nodes(dep, orderingI)
            if not dep.obj.usedBy[0]:
                removed.add(dep.obj)
            n._removeInput(orderingI.in_i)
            modified = True
    if modified:
        worklist.append(n)
    return modified

    
def netlistOrderingReduce(n: HlsNetNodeExplicitSync, threads: HlsNetlistAnalysisPassDataThreadsForBlocks):
    """
    remove ordering if it is redundant information
    """
    for orderingI in tuple(n.iterOrderingInputs()):
        orderingI: HlsNetNodeIn
        t0 = threads.threadPerNode.get(n, None)
        if t0 is None:
            # not sure about parent thread, skip this
            continue

        depOo = n.dependsOn[orderingI.in_i]
        depObj: HlsNetNodeExplicitSync = depOo.obj
        assert isinstance(depObj, (HlsNetNodeExplicitSync, HlsNetNodeDelayClkTick)), (
            depObj, "ordering should be used only for HlsNetNodeExplicitSync instances")
        t1 = threads.threadPerNode.get(depObj, None)

        if t1 is None:
            # not sure about other parent thread, skip this
            continue

        if t0 is t1:
            # is in same thread => rm this association because there is data dependency which asserts the ordering
            assert n is not depObj, n
            if isinstance(n, HlsNetNodeRead) and isinstance(depObj, HlsNetNodeRead):
                n: HlsNetNodeRead
                if n.src is depObj.src:
                    # can not ignore order of reads from same volatile source
                    continue

            elif isinstance(n, HlsNetNodeWrite) and isinstance(depObj, HlsNetNodeWrite):
                n: HlsNetNodeWrite
                if n.dst is depObj.dst:
                    # can not ignore order of writes to same volatile destination
                    continue

            elif isinstance(n, HlsNetNodeWriteBackwardEdge) and depObj is n.associated_read:
                # can not ignore order of operations with the same channel
                continue

            netlistExplicitSyncOrderingBypass(orderingI)
