from collections import deque
from itertools import islice
from typing import Set, Union, List, Optional

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bitsVal import BitsVal
from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.netlist.analysis.dataThreadsForBlocks import HlsNetlistAnalysisPassDataThreadsForBlocks
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge, \
    HlsNetNodeReadBackwardEdge, HlsNetNodeReadControlBackwardEdge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.orderable import HOrderingVoidT, _VoidValue
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, unlink_hls_nodes, \
    link_hls_nodes, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf, \
    replaceOperatorNodeWith, \
    operationTakesMoreThan1Clk, \
    transferHlsNetNodeExplicitSyncOrdering, disconnectAllInputs, addAllUsersToWorklist
from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck

# :note: not working ignores parallel sync objects and this actualy does hoist of the flags, which is done elsewhere
#def netlistReduceExplicitSyncUseless(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode],
#                                     removed: Set[HlsNetNode],
#                                     syncDeps: Optional[HlsNetlistAnalysisPassSyncDependency]):
#    """
#    Remove HlsNetNodeExplicitSync if its flags do not have any effect.
#    
#    :return: True if this node n was removed
#    """
#    #traceChanges = syncDeps is not None 
#    
#    if (n.skipWhen is None or getConstDriverOf(n.skipWhen) is not None) and (
#        n.extraCond is None or getConstDriverOf(n.extraCond) is not None):
#        syncedDep: HlsNetNodeOut = n.dependsOn[0]
#        # remove synchronization node without any synchronization flag specified
#        syncedObj = syncedDep.obj
#        if n.skipWhen is not None and int(n.dependsOn[n.skipWhen.in_i].obj.val) != 0:
#            if isinstance(syncedObj, HlsNetNodeExplicitSync):
#                dep = n.dependsOn[n.skipWhen.in_i] 
#                syncedDep.obj.addControlSerialSkipWhen(dep)
#                #if traceChanges:
#                #    syncDeps.addAllUsersToInDepChange(dep.obj)
#                #    # newDep = n.dependsOn[n.skipWhen.in_i] 
#                #    syncDeps.addOutUseChange(dep.obj)
#            else:
#                return False
#
#        if n.extraCond is not None and int(n.dependsOn[n.extraCond.in_i].obj.val) != 1:
#            if isinstance(syncedObj, HlsNetNodeExplicitSync):
#                dep = n.dependsOn[n.extraCond.in_i]
#                syncedDep.obj.addControlSerialExtraCond(dep)
#                #if traceChanges:
#                #    syncDeps.addAllUsersToInDepChange(dep.obj)
#                #    syncDeps.addOutUseChange(dep.obj)
#            else:
#                #if traceChanges:
#                #    syncDeps.commitChanges()
#                return False
#        
#        _, orderingOutUses = n._outputs.pop(), n.usedBy.pop()
#        if orderingOutUses:
#            for orderingIn in n.iterOrderingInputs():
#                orderingDep = n.dependsOn[orderingIn.in_i]
#                #if traceChanges:
#                #    syncDeps.addOutUseChange(orderingDep.obj)
#                for u in orderingOutUses:
#                    u: HlsNetNodeIn
#                    u.replaceDriverInInputOnly(orderingDep, False)  # because n will be removed
#                    #if traceChanges:
#                    #    syncDeps.addInDepChange(u.obj)
#
#        #if traceChanges:
#        #    syncDeps.addAllUsersToInDepChange(n)
#
#        replaceOperatorNodeWith(n, syncedDep, worklist, removed)
#        #if traceChanges:
#        #    syncDeps.onNodeRemove(n)
#        #    syncDeps.addOutUseChange(syncedDep.obj)
#        #    syncDeps.commitChanges()
#
#        return True

# def netlistReduceExplicitSyncWithoutIo(n: HlsNetNodeExplicitSync,
#                                       worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode],
#                                       syncDeps: HlsNetlistAnalysisPassSyncDependency):
#    # code duplication
#    # elif not n.usedBy[0] and not isHlsNetNodeExplicitSyncFlagsRequred(n):
#    #    # remove whole node if not synchronizing anything
#    #    for i in n._inputs:
#    #        dep = n.dependsOn[i.in_i]
#    #        dep.obj.usedBy[dep.out_i].remove(i)
#    #        worklist.append(dep.obj)
#    #    
#    #    removed.add(n)
#    #    return False
#    syncedDep: HlsNetNodeOut = n.dependsOn[0]   
#    if not isConnectedToAnyIo(syncedDep, syncDeps):
#        # not synchronizing anything because there is no IO involved in input
#        assert len(n._outputs) == 2, n
#        
#        # transfer all ordering inputs from "n" to all users
#        oo = n.getOrderingOutPort()
#        assert oo.out_i == 1
#        orderingDeps = tuple(n.dependsOn[oi.in_i] for oi in n.iterOrderingInputs())
#        for u in tuple(n.usedBy[oo.out_i]):
#            unlink_hls_nodes(oo, u)
#            # and add dependencies from depObj to orderingI.obj
#            uObj: HlsNetNodeExplicitSync = u.obj
#            userOrderingDeps = set(uObj.dependsOn[uoi.in_i] for uoi in u.iterOrderingInputs())
#            for oi in orderingDeps:
#                oi: HlsNetNodeOut
#                if oi in userOrderingDeps:
#                    continue
#                else:
#                    userOrderingDeps.add(oi)
#                    uoi = uObj._addInput("orderingIn")
#                    link_hls_nodes(oi, uoi)
#    
#        replaceOperatorNodeWith(n, syncedDep, worklist, removed)
#        return True
#
#    elif getConstDriverOf(n._inputs[0]) is not None and all(not use for use in islice(n.usedBy, 1, None)):
#        # input is constant and ordering is not used
#        for _ in range(len(n.usedBy) - 1):
#            n.usedBy.pop()
#            n._outputs.pop()
#        if n._associatedReadSync is not None:
#            raise NotImplementedError(n)
#
#        replaceOperatorNodeWith(n, syncedDep, worklist, removed)
#        return True

# def inputDriverReachesSyncNode(inp: Optional[HlsNetNodeIn], node: HlsNetNode):
#    if inp is None:
#        return False
#    dep = inp.obj.dependsOn[inp.in_i]
#    seen = set()
#    toSearch = deque((dep,))
#    while toSearch:
#        dep = toSearch.popleft()
#        if dep.obj in seen:
#            continue
#        else:
#            seen.add(dep.obj)
#
#        if dep.obj is node:
#            return True
#        else:
#            toSearch.extend(dep.obj.dependsOn)
#
#    return False
#
#
# def netlistReduceExplicitSyncMergeToPredecessor(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
#    syncedDep: HlsNetNodeOut = n.dependsOn[0]
#    syncedDepObj = syncedDep.obj
#    if isinstance(syncedDepObj, HlsNetNodeExplicitSync) and \
#            len(syncedDepObj.usedBy[0]) == 1 and \
#            not operationTakesMoreThan1Clk(syncedDepObj) and \
#            (syncedDepObj.extraCond or syncedDepObj.skipWhen) and \
#            not inputDriverReachesSyncNode(n.skipWhen, syncedDepObj) and \
#            not inputDriverReachesSyncNode(n.extraCond, syncedDepObj):
#        # merge sync to previous object if possible
#        # avoid merging if has multiple successors or
#        #   successor is forcefully in different clock cycle or
#        #   successor is suitable for remove
#        syncedDepObj: Union[HlsNetNodeRead, HlsNetNodeWrite]
#        trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(n, syncedDepObj)
#        transferHlsNetNodeExplicitSyncOrdering(n, syncedDepObj)
#        unlink_hls_nodes(syncedDep, n._inputs[0])
#        syncedDepUses = syncedDepObj.usedBy[syncedDep.out_i]
#        for u in n.usedBy[0]:
#            u.obj.dependsOn[u.in_i] = syncedDep
#            syncedDepUses.append(u)
#        n.usedBy[0].clear()
#
#        removed.add(n)
#        return True

# def netlistReduceExplicitSyncMergeToSuccessor(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
#    if len(n.usedBy[0]) == 1 and isinstance(n.usedBy[0][0].obj, HlsNetNodeExplicitSync):
#        # merge this node into successor if possible
#        suc0: HlsNetNodeExplicitSync = n.usedBy[0][0].obj
#        trasferHlsNetNodeExplicitSyncFlagsSeriallyConnected(n, suc0)
#        transferHlsNetNodeExplicitSyncOrdering(n, suc0)
#        o = n.dependsOn[0]
#        prevI = n._inputs[0]
#        newI = suc0._inputs[0]
#        newI.replaceDriver(o)
#        o.obj.usedBy[0].remove(prevI)
#        removed.add(n)
#        return True


def netlistReduceReadReadSyncWithReadOfValidNB(n: HlsNetNodeRead,
                                               worklist: UniqList[HlsNetNode],
                                               removed: Set[HlsNetNode]):
    rs = n._associatedReadSync
    if rs:
        if rs.usedBy[0]:
            # replace _associatedReadSync with _validNB
            vld = n.getValidNB()
            replaceOperatorNodeWith(rs, vld, worklist, removed)
        else:
            # remove _associatedReadSync
            disconnectAllInputs(rs, worklist)
        
        n._associatedReadSync = None
        removed.add(rs)
        return True

    else:
        return False
