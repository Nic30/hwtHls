from typing import Set, Optional

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes, \
    link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import removeExplicitSync


def netlistReduceExplicitSyncConditions(dbgTracer: DebugTracer, n: HlsNetNodeExplicitSync,
                                        worklist: Optional[UniqList[HlsNetNode]],
                                        removed: Set[HlsNetNode]):
    """
    Remove skipWhen extraCond ports if they are useless and remove n if it has no sync flags and is directly HlsNetNodeExplicitSync instance.
    """
    with dbgTracer.scoped(netlistReduceExplicitSyncConditions, n):
        modified = False
        if n.skipWhen is not None:
            dep = n.dependsOn[n.skipWhen.in_i]
            if isinstance(dep.obj, HlsNetNodeConst):
                if int(dep.obj.val) == 0:
                    # ("Constant skipWhen condition must be 0, because otherwise the channel is always skipped", n, dep.obj)
                    dep.obj.usedBy[dep.out_i].remove(n.skipWhen)
                    if worklist is not None:
                        worklist.append(dep.obj)
                    n._removeInput(n.skipWhen.in_i)
                    n.skipWhen = None
                    modified = True
                    dbgTracer.log("rm skipWhen")
    
        if n.extraCond is not None:
            dep = n.dependsOn[n.extraCond.in_i]
            if isinstance(dep.obj, HlsNetNodeConst):
                if int(dep.obj.val) == 1:
                    # ("Constant extraCond must be 1, because otherwise the channel is always blocked", n, dep.obj)
                    dep.obj.usedBy[dep.out_i].remove(n.extraCond)
                    if worklist is not None:
                        worklist.append(dep.obj)
                    n._removeInput(n.extraCond.in_i)
                    n.extraCond = None
                    modified = True
                    dbgTracer.log("rm extraCond")
    
        if n.__class__ is HlsNetNodeExplicitSync and n.skipWhen is None and n.extraCond is None:
            dbgTracer.log("rm node")
            removeExplicitSync(dbgTracer, n, worklist, removed)
            modified = True
    
        return modified


def removeSyncReadOfRead(r: HlsNetNodeRead, removed: Set[HlsNetNode]):
    unlink_hls_nodes(r._outputs[0], r._associatedReadSync._inputs[0])
    removed.add(r._associatedReadSync)
    r._associatedReadSync = None


def isAndedToExpression(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    if expr is valToSearch:
        return True
    elif isinstance(expr.obj, HlsNetNodeOperator) and expr.obj.operator == AllOps.AND:
        for o in expr.obj.dependsOn:
            if isAndedToExpression(valToSearch, o):
                return True
        
    return False


def createAndExpressionOmmitingInput(valToOmmit: HlsNetNodeOut, expr: HlsNetNodeOut):
    if expr is valToOmmit:
        return None
    elif isinstance(expr.obj, HlsNetNodeOperator) and expr.obj.operator == AllOps.AND:
        o0, o1 = expr.obj.dependsOn
        newO0 = createAndExpressionOmmitingInput(valToOmmit, o0)
        newO1 = createAndExpressionOmmitingInput(valToOmmit, o1)
        if newO0 is None:
            return newO1
        elif newO1 is None:
            return newO0
        elif o0 is newO0 and o1 is newO1:
            return expr
        else:
            return expr.obj.netlist.builder.buildAnd(newO0, newO1)
    else:
        return expr


def netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTracer: DebugTracer,
                                                              n: HlsNetNodeExplicitSync,
                                                              worklist: UniqList[HlsNetNode],
                                                              removed: Set[HlsNetNode],
                                                              reachDb: HlsNetlistAnalysisPassReachabilility):
    assert n.__class__ is HlsNetNodeExplicitSync, n
    syncedDep: HlsNetNodeOut = n.dependsOn[0]
    rw = syncedDep.obj
    if n.skipWhen is None or not isinstance(rw, (HlsNetNodeRead, HlsNetNodeWrite)):
        return False
    # [todo] cover the case where skipWhen=1 
    modified = False
    # try extract non blocking read
    # 2 usedBy for _associatedReadSync and this node "n"
    assert rw._associatedReadSync is None, rw
    with dbgTracer.scoped(netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite, n):
        if not isinstance(rw, HlsNetNodeRead) or rw._validNB is None or not rw._isBlocking or len(rw.usedBy[syncedDep.out_i]) > 2:
            return modified
    
        if n.extraCond is None:
            ec = None
        else:
            ec = n.dependsOn[n.extraCond.in_i]
    
        validNB = rw._validNB
        sw = n.dependsOn[n.skipWhen.in_i]
        if ((ec is None or isAndedToExpression(validNB, ec)) and
                isinstance(sw.obj, HlsNetNodeOperator) and
                sw.obj.operator is AllOps.NOT and
                isAndedToExpression(validNB, sw.obj.dependsOn[0]) and
                isinstance(rw, HlsNetNodeRead)):
            # [todo] isAndedToExpression is not sufficient we should that it is not non-trivially reachable
            #        from any term in "and" so we do not create cycle in DAG if we transplant this "and" to an input of n
            r: HlsNetNodeRead = rw
            dbgTracer.log(("Non-blocking associated with read ", r))

            # Try extracting non-blocking read from pattern:
            # x = read()
            # x.explicitSync(extraCond=x.valid, skipWhen=~x.valid)
            
            # ec == validNB
            # sw == ~validNB
            # replace validNB in ec/sw expression with 1 only only for this "n"
            # if used anywhere else replace with r.valid,
            # transfer ec/sw from this "n" to parent read "r"
            dataUses = tuple(n.usedBy[0])
            data = n._outputs[0]
            assert n._associatedReadSync is None, "Should already be removed."
            # for _n in (n, r):
            #    reachDb.addAllDepsToOutUseChange(_n)
            #    reachDb.addAllUsersToInDepChange(_n)
            if ec is not None:
                newEc = createAndExpressionOmmitingInput(validNB, ec)
                # reachDb.addOutUseChange(ec.obj)
                unlink_hls_nodes(ec, n.extraCond)
                if newEc is not None:
                    r.addControlSerialExtraCond(newEc)
                dbgTracer.log(("update extraCond to", newEc))
    
            # reachDb.addOutUseChange(sw.obj)
            unlink_hls_nodes(sw, n.skipWhen)
            newSw_n = createAndExpressionOmmitingInput(validNB, sw.obj.dependsOn[0])
            if newSw_n is not None:
                newSw = n.netlist.builder.buildNot(newSw_n)
                r.addControlSerialSkipWhen(newSw)
                dbgTracer.log(("update skipWhen to", newSw))
                
            # vldUses = tuple(r.usedBy[r._valid.out_i])
            #
            # for u in vldUses:
            #    unlink_hls_nodes(vld, u)
    
            # reachDb.addOutUseChange(n)
            for u in dataUses:
                # reachDb.addInDepChange(u.obj)
                unlink_hls_nodes(data, u)
    
            # reachDb.addOutUseChange(r)
            unlink_hls_nodes(n.dependsOn[0], n._inputs[0])
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, removed)
            
            r.setNonBlocking()
            data = syncedDep
            # vld = r._valid
            # for u in vldUses:
            #    link_hls_nodes(vld, u)
            #    worklist.append(u.obj)
    
            for u in dataUses:
                link_hls_nodes(data, u)
                worklist.append(u.obj)
            
            removed.add(n)
            dbgTracer.log("rm")
            netlistReduceExplicitSyncConditions(dbgTracer, r, worklist, removed)
            return True
    
        # elif (isinstance(syncedDep.obj, HlsNetNodeOperator) and
        #      syncedDep.obj.operator is AllOps.AND and
        #      (syncedDep.dependsOn == (r._outputs[0], vld) or 
        #       syncedDep.dependsOn == (vld, r._outputs[0]))):
        #    # r = read()
        #    # r0 = r.data & r.valid
        #    # n = r0.explicitSync()
        return modified


def tryExtractNonBlockingVoidRead(n: HlsNetNodeRead, readSync:HlsNetNodeReadSync,
                                  worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    assert readSync is n._associatedReadSync, (n, n._associatedReadSync, readSync)
    if len(n.usedBy[0]) == 1 and n.extraCond is None and n.skipWhen is None:
        n.setNonBlocking()
        n.netlist.builder.replaceOutput(readSync._outputs[0], n._valid, True)
        removeSyncReadOfRead(n, removed)
        worklist.extend(u.obj for u in n.usedBy[n._valid.out_i])
        return True

    return False
