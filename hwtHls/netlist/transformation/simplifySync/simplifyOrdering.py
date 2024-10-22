from typing import Set, Sequence, Optional, Tuple

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData, HVoidOrdering, \
    HdlType_isVoid, _HVoidOrdering
from hwtHls.netlist.nodes.aggregateUtils import iterUsersIgnoringHierarchy, \
    removeInputIgnoringHierarchy
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HlsNetNodeOrderable
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, \
    HlsNetNodeOut, HlsNetNodeOutLazy
from hwtHls.netlist.nodes.portsUtils import HlsNetNodeOut_connectHlsIn_crossingHierarchy


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
                d.connectHlsIn(nOi)
        else:
            assert isinstance(d, HlsNetNodeOutLazy), d
            if d in nOrderingUses:
                # prevent ordering duplication
                continue
            else:
                nOrderingUses.add(d)
                nOi = n._addInput("orderingIn", addDefaultScheduling=True)
                d.connectHlsIn(nOi)

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
        time = predObj.scheduledOut[predOo.out_i] if predObj.scheduledOut else None
    else:
        assert isinstance(predOo, HlsNetNodeOutLazy), predOo
        predOoUses = predOo.dependent_inputs
        time = None

    if disconnectInput:
        # rm orderingI of node n
        # predOoUses.remove(orderingI)
        # assert orderingI not in predOoUses, (orderingI, "was multiple times in usedBy")
        orderingI.disconnectFromHlsOut(predOo)
        n._removeInput(orderingI.in_i)

    # if isNormalPort:
    #    raise AssertionError("The ordering should not be added to n")
    #    _explicitSyncAddUniqueOrdering(n, (predObj.dependsOn[oi.in_i] for oi in predObj.iterOrderingInputs()), None)

    # add ordering uses from n to nodes with ordering dependency on n
    oo = n.getOrderingOutPort()
    predOrderingUses: Set[HlsNetNodeExplicitSync] = set(u.obj for u in predOoUses)
    for u in iterUsersIgnoringHierarchy(oo, set()):
        u: HlsNetNodeIn
        if u.obj in predOrderingUses:
            # prevent ordering duplication
            continue
        else:
            assert u.obj is not n, (n, "there should be no cycle")
            predOrderingUses.add(u.obj)
            in_ = u.obj._addInput("orderingIn", addDefaultScheduling=True)
            HlsNetNodeOut_connectHlsIn_crossingHierarchy(predOo, in_, "ordering", time=time)


def netlistExplicitSyncOrderingOutUsesDiscard(n: HlsNetNodeExplicitSync, worklist: Optional[SetList[HlsNetNode]]):
    """
    Disconnect uses of ordering output of n and remove all ports which were originally connected.
    """
    o = n.getOrderingOutPort()
    for in_ in tuple(n.usedBy[o.out_i]):
        in_: HlsNetNodeIn
        in_.disconnectFromHlsOut(o)
        removeInputIgnoringHierarchy(in_, worklist)

    # n.usedBy[o.out_i].clear()


def netlistTrivialOrderingReduce(n: HlsNetNodeExplicitSync, worklist: SetList[HlsNetNode]):
    modified = False
    for orderingI in tuple(n.iterOrderingInputs()):
        orderingI: HlsNetNodeIn
        dep = n.dependsOn[orderingI.in_i]
        if isinstance(dep.obj, HlsNetNodeConst):
            orderingI.disconnectFromHlsOut(dep)
            n._removeInput(orderingI.in_i)
            if not dep.obj.usedBy[0]:
                dep.obj.markAsRemoved()
            modified = True

        if dep._dtype != HVoidOrdering:
            continue

        if HdlType_isNonData(dep._dtype) and isinstance(dep.obj, HlsNetNodeConst):
            orderingI.disconnectFromHlsOut(dep)
            if not dep.obj.usedBy[0]:
                dep.obj.markAsRemoved()
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
                            orderingI.disconnectFromHlsOut(dep)
                            n._removeInput(orderingI.in_i)
                            break
                else:
                    key = (t, dep.obj)
                    if key in seen:
                        dbgTracer.log(("rm duplicit link from ", dep.obj._id, orderingI.name))
                        orderingI.disconnectFromHlsOut(dep)
                        n._removeInput(orderingI.in_i)
                    else:
                        seen.add(key)

