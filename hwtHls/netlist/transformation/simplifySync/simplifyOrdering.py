from typing import Set, Sequence, Optional, Tuple

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData, HVoidOrdering, \
    HdlType_isVoid, _HVoidOrdering
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, link_hls_nodes, \
    HlsNetNodeOut, unlink_hls_nodes, HlsNetNodeOutLazy


def netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer: DebugTracer, n: HlsNetNodeOrderable,
                                                   worklist: Optional[SetList[HlsNetNode]],
                                                   disconnectPredecessors: bool=True,
                                                   disconnectSuccesors: bool=True):
    """
    Using orderingIn and orderingOut node may be connected to other orderable nodes.
    Mentioned ports can not be just disconnected instead they need to be transitively reconnected
    to preserver global ordering of nodes. This is done by this function.
    """
    assert disconnectPredecessors or disconnectSuccesors, "At least one must be set otherwise this function would do nothing and in that case it should not be called at all."

    with dbgTracer.scoped(netlistExplicitSyncDisconnectFromOrderingChain, n):
        if isinstance(n, HlsNetNodeExplicitSync):
            assert n._inputOfCluster is None, ("This function should be used only before IO clusters were constructed", n)
            assert n._outputOfCluster is None, ("This function should be used only before IO clusters were constructed", n)
        for orderingI in tuple(n.iterOrderingInputs()):
            dep = n.dependsOn[orderingI.in_i]
            assert dep is not None, ("Ordering input ports should be removed if they are disconnected", orderingI)
            if worklist is not None:
                worklist.append(dep.obj)
            netlistExplicitSyncOrderingBypass(orderingI, disconnectPredecessors)

        if disconnectSuccesors:
            netlistExplicitSyncOrderingOutUsesDiscard(n, worklist)


def _explicitSyncAddUniqueOrdering(n: HlsNetNodeExplicitSync,
                                   newOrderingDeps: Sequence[HlsNetNodeOut],
                                   nOrderingUses: Optional[Set[HlsNetNodeExplicitSync]]):
    """
    Add ordering dependencies to node "n" from newOrderingDeps

    :param n: node were to add ordering input ports and link them with newOrderingDeps.
    :param newOrderingDeps: sequence or ordering dependencies which should be added.
    :param nOrderingUses: set of current ordering uses to avoid add of redundant ordering edges.
    """
    # collect already present ordering
    if nOrderingUses is None:
        nOrderingUses = set()
        for oi in n.iterOrderingInputs():
            nOrderingUses.add(n.dependsOn[oi.in_i].obj)

    # add dependencies from depObj to n
    for d in newOrderingDeps:
        if isinstance(d, HlsNetNodeOut):
            if d.obj in nOrderingUses:
                # prevent ordering duplication
                continue
            else:
                nOrderingUses.add(d.obj)
                nOi = n._addInput("orderingIn", addDefaultScheduling=True)
                link_hls_nodes(d, nOi)
        else:
            assert isinstance(d, HlsNetNodeOutLazy), d
            if d in nOrderingUses:
                # prevent ordering duplication
                continue
            else:
                nOrderingUses.add(d)
                nOi = n._addInput("orderingIn", addDefaultScheduling=True)
                link_hls_nodes(d, nOi)

    return nOrderingUses


def netlistExplicitSyncOrderingBypass(orderingI: HlsNetNodeIn, disconnectInput: bool):
    """
    Used to cancel ordering connection for nodes which do have ordering guaranteed trough other means

    Distribute ordering dependencies from dependency of this input "dep" to all ordering user of this node "n"
    and forward ordering users of "n" ordering output port to "dep".

    .. code-block:: text

       --v
        pred -> n -> use

    to
    .. code-block:: text

     ----+----+
         v    v
        pred  n -> use
         |----------^

    or
     ----+
         v
        pred   n -> use
         |----------^

    """
    n = orderingI.obj
    predOo = n.dependsOn[orderingI.in_i]
    isNormalPort = isinstance(predOo, HlsNetNodeOut)
    if isNormalPort:
        predObj = predOo.obj
        predOoUses = predObj.usedBy[predOo.out_i]
    else:
        assert isinstance(predOo, HlsNetNodeOutLazy), predOo
        predOoUses = predOo.dependent_inputs

    if disconnectInput:
        # rm orderingI of node n
        predOoUses.remove(orderingI)
        assert orderingI not in predOoUses, (orderingI, "was multiple times in usedBy")
        n._removeInput(orderingI.in_i)

    # if isNormalPort:
    #    raise AssertionError("The ordering should not be added to n")
    #    _explicitSyncAddUniqueOrdering(n, (predObj.dependsOn[oi.in_i] for oi in predObj.iterOrderingInputs()), None)

    # add ordering uses from n to nodes with ordering dependency on n
    oo = n.getOrderingOutPort()
    predOrderingUses: Set[HlsNetNodeExplicitSync] = set(u.obj for u in predOoUses)
    for u in n.usedBy[oo.out_i]:
        u: HlsNetNodeIn
        if u.obj in predOrderingUses:
            # prevent ordering duplication
            continue
        else:
            assert u.obj is not n, (n, "there should be no cycle")
            predOrderingUses.add(u.obj)
            i = u.obj._addInput("orderingIn", addDefaultScheduling=True)
            link_hls_nodes(predOo, i)


def netlistExplicitSyncOrderingOutUsesDiscard(n: HlsNetNodeExplicitSync, worklist: Optional[SetList[HlsNetNode]]):
    """
    Disconnect uses of ordering output of n and remove all ports which were originally connected.
    """
    o = n.getOrderingOutPort()
    for i in tuple(n.usedBy[o.out_i]):
        i: HlsNetNodeIn
        unlink_hls_nodes(o, i)
        i.obj._removeInput(i.in_i)
        if worklist is not None:
            worklist.append(i.obj)

    # n.usedBy[o.out_i].clear()


def netlistTrivialOrderingReduce(n: HlsNetNodeExplicitSync, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
    modified = False
    for orderingI in tuple(n.iterOrderingInputs()):
        orderingI: HlsNetNodeIn
        dep = n.dependsOn[orderingI.in_i]
        if isinstance(dep.obj, HlsNetNodeConst):
            unlink_hls_nodes(dep, orderingI)
            n._removeInput(orderingI.in_i)
            if not dep.obj.usedBy[0]:
                removed.add(dep.obj)
            modified = True

        if dep._dtype != HVoidOrdering:
            continue

        if HdlType_isNonData(dep._dtype) and isinstance(dep.obj, HlsNetNodeConst):
            unlink_hls_nodes(dep, orderingI)
            if not dep.obj.usedBy[0]:
                removed.add(dep.obj)
            n._removeInput(orderingI.in_i)
            modified = True

    if modified:
        worklist.append(n)

    return modified


def netlistOrderingReduce(dbgTracer: DebugTracer, n: HlsNetNodeExplicitSync, reachDb: HlsNetlistAnalysisPassReachability):
    """
    remove ordering if it is redundant information
    """
    with dbgTracer.scoped(netlistOrderingReduce, n):
        seen: Set[Tuple[_HVoidOrdering, HlsNetNode]] = set()
        for orderingI in tuple(n.iterOrderingInputs()):
            orderingI: HlsNetNodeIn
            dep = n.dependsOn[orderingI.in_i]
            t = dep._dtype
            if HdlType_isVoid(t):
                if t == HVoidOrdering:
                    # remove this link if there is an alternative path from dep.obj to n
                    for o in dep.obj._outputs:
                        if o is not dep and reachDb.doesReachTo(o, n):
                            dbgTracer.log(("rm link from ", dep.obj._id, orderingI.name))
                            unlink_hls_nodes(dep, orderingI)
                            n._removeInput(orderingI.in_i)
                            break
                else:
                    key = (t, dep.obj)
                    if key in seen:
                        dbgTracer.log(("rm duplicit link from ", dep.obj._id, orderingI.name))
                        unlink_hls_nodes(dep, orderingI)
                        n._removeInput(orderingI.in_i)
                    else:
                        seen.add(key)

