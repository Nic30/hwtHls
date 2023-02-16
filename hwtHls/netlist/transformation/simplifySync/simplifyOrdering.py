from typing import Set, Sequence, Optional

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isNonData, HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, link_hls_nodes, \
    HlsNetNodeOut, unlink_hls_nodes
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility


def netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer: DebugTracer, n: HlsNetNodeExplicitSync, removed: Set[HlsNetNode],
                                                   disconnectPredecessors: bool=True,
                                                   disconnectSuccesors: bool=True):
    """
    :attention: n is not added to removed, only a HlsNetNodeIoClusterCore instances are added to removed
        if disconnecting from ordering caused IoClusters to collapse
    """
    assert disconnectPredecessors or disconnectSuccesors
    
    with dbgTracer.scoped(netlistExplicitSyncDisconnectFromOrderingChain, n):
        for orderingI in tuple(n.iterOrderingInputs()):
            dep = n.dependsOn[orderingI.in_i]
            assert not isinstance(dep.obj, HlsNetNodeIoClusterCore), ("_outputOfCluster/_inputOfCluster are only ports where HlsNetNodeIoClusterCore should be connected and these ports should no be returned from iterOrderingInputs()", dep)
            netlistExplicitSyncOrderingBypass(orderingI, disconnectPredecessors)

        succIoCluster: Optional[HlsNetNodeIoClusterCore] = None if n._outputOfCluster is None else n.dependsOn[n._outputOfCluster.in_i].obj
        predIoCluster: Optional[HlsNetNodeIoClusterCore] = None if n._inputOfCluster is None else n.dependsOn[n._inputOfCluster.in_i].obj
        assert (predIoCluster is None and succIoCluster is None) or (predIoCluster is not None and succIoCluster is not None), \
            ("If there are IoClusters in the netlist each ExplicitSync must be connected to input and output cluster")

        if predIoCluster:
            if not disconnectPredecessors or not disconnectSuccesors:
                raise NotImplementedError()

            if succIoCluster is predIoCluster:
                dbgTracer.log(("rm ", n._id, " from cluster ", predIoCluster._id))
                for i in (n._outputOfCluster, n._inputOfCluster):
                    unlink_hls_nodes(n.dependsOn[i.in_i], i)
                if not any(predIoCluster.usedBy):
                    removed.add(predIoCluster)
                    dbgTracer.log(("rm empty cluster", predIoCluster._id))

            else:
                dbgTracer.log(("merge io clusters", predIoCluster._id, " to ", succIoCluster._id))
    
                # :note: it is guaranged that predIoCluster < succIoCluster => it is safe to transfer io between io clusters
                # each sync/io node can be input and output (separetely) just in a single node
                curInputs = {use.obj: use for use in succIoCluster.usedBy[succIoCluster.inputNodePort.out_i]}
                # transfer inputs of predecessor cluster to successor
                predInPort = predIoCluster.inputNodePort
                sucInPort = succIoCluster.inputNodePort
                for use in tuple(predIoCluster.usedBy[predInPort.out_i]):
                    unlink_hls_nodes(predInPort, use)
                    if use.obj is n:
                        # skip because this is the node we are removing
                        continue
                    link_hls_nodes(sucInPort, use)
    
                # transfer outputs and potentially remove from successor inputs
                predOutPort = predIoCluster.outputNodePort
                succOutPort = succIoCluster.outputNodePort
                for useOut in tuple(predIoCluster.usedBy[predOutPort.out_i]):
                    # :note: user is an output of predIoCluster
                    useAsInput = curInputs.get(useOut.obj, None)
                    if useAsInput is not None:
                        # input became output
                        unlink_hls_nodes(sucInPort, useAsInput)
                        useAsInput.obj._removeInput(useAsInput.in_i)
    
                    unlink_hls_nodes(predOutPort, useOut)
                    if useOut.obj is n:
                        # skip because this is the node we are removing
                        continue
                    link_hls_nodes(succOutPort, useOut)
                
                for i in (n._outputOfCluster, n._inputOfCluster):
                    dep = n.dependsOn[i.in_i]
                    if dep is not None:
                        unlink_hls_nodes(dep, i)
                removed.add(predIoCluster)

        else:
            dbgTracer.log("rm not connected to any io cluster")
        
        if disconnectSuccesors:
            netlistExplicitSyncOrderingOutUsesDiscard(n)

    
def _explicitSyncAddUniqueOrdering(n: HlsNetNodeExplicitSync,
                                   newOrderingDeps: Sequence[HlsNetNodeOut],
                                   nOrderingUses: Optional[Set[HlsNetNodeExplicitSync]]):
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


def netlistExplicitSyncOrderingBypass(orderingI: HlsNetNodeIn, disconnectInput: bool):
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
         
    or 
     ----+
         v     
        dep   n -> use
         |----------^  
         
    """
    n = orderingI.obj
    # rm orderingI of node n
    depOo = n.dependsOn[orderingI.in_i]
    depObj = depOo.obj
    if disconnectInput:
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
        if isinstance(dep.obj, HlsNetNodeConst):
            unlink_hls_nodes(dep, orderingI)
            n._removeInput(orderingI.in_i)
            if not dep.obj.usedBy[0]:
                removed.add(dep.obj)
            modified = True

        if dep._dtype != HVoidOrdering or isinstance(dep.obj, HlsNetNodeIoClusterCore):
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

    
def netlistOrderingReduce(dbgTracer: DebugTracer, n: HlsNetNodeExplicitSync, reachDb: HlsNetlistAnalysisPassReachabilility):
    """
    remove ordering if it is redundant information
    """
    with dbgTracer.scoped(netlistOrderingReduce, n):
        for orderingI in tuple(n.iterOrderingInputs()):
            orderingI: HlsNetNodeIn
            dep = n.dependsOn[orderingI.in_i]
            if dep._dtype != HVoidOrdering or isinstance(dep.obj, HlsNetNodeIoClusterCore):
                continue
            # remove this link if there is an alternative path from dep.obj to n
            for o in dep.obj._outputs:
                if o is not dep and reachDb.doesReachTo(o, n):
                    dbgTracer.log(("rm link from ", dep.obj._id, orderingI.name))
                    unlink_hls_nodes(dep, orderingI)
                    n._removeInput(orderingI.in_i)
                    break
