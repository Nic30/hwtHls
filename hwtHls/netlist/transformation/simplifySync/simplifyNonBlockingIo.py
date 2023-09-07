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
from hwtHls.netlist.builder import HlsNetlistBuilder


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
                    unlink_hls_nodes(dep, n.skipWhen)
                    if worklist is not None:
                        worklist.append(dep.obj)
                        worklist.append(n)
                    n._removeInput(n.skipWhen.in_i)
                    modified = True
                    dbgTracer.log("rm skipWhen")

        if n.extraCond is not None:
            dep = n.dependsOn[n.extraCond.in_i]
            if isinstance(dep.obj, HlsNetNodeConst):
                if int(dep.obj.val) == 1:
                    # ("Constant extraCond must be 1, because otherwise the channel is always blocked", n, dep.obj)
                    unlink_hls_nodes(dep, n.extraCond)
                    if worklist is not None:
                        worklist.append(dep.obj)
                        worklist.append(n)
                    n._removeInput(n.extraCond.in_i)
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
    """
    Check if expression is in format expr = And(.., valToSearch, ...)
    """
    if expr is valToSearch:
        return True
    elif isinstance(expr.obj, HlsNetNodeOperator) and expr.obj.operator == AllOps.AND:
        for o in expr.obj.dependsOn:
            if isAndedToExpression(valToSearch, o):
                return True

    return False


def isAndedToNodAndExpr(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    """
    Check if expression is in format expr = ~And(.., valToSearch, ...)
    """
    return isinstance(expr.obj, HlsNetNodeOperator) and \
           expr.obj.operator is AllOps.NOT and \
           isAndedToExpression(valToSearch, expr.obj.dependsOn[0])


def isNot(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    return isinstance(expr.obj, HlsNetNodeOperator) and \
           expr.obj.operator is AllOps.NOT and \
           expr.obj.dependsOn[0] is valToSearch


def isNotOredToOrExpr(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    """
    Check if expression is in format expr = Or(.., ~valToSearch, ...)
    """
    if isNot(valToSearch, expr):
        return True
    elif isinstance(expr.obj, HlsNetNodeOperator) and expr.obj.operator == AllOps.OR:
        for o in expr.obj.dependsOn:
            if isNotOredToOrExpr(valToSearch, o):
                return True

    return False


def createLogicalExpressionOmmitingInput(valToOmmit: HlsNetNodeOut, expr: HlsNetNodeOut):
    if expr is valToOmmit:
        return None
    elif isinstance(expr.obj, HlsNetNodeOperator):
        op = expr.obj.operator
        if op == AllOps.AND or op == AllOps.OR:
            o0, o1 = expr.obj.dependsOn
            newO0 = createLogicalExpressionOmmitingInput(valToOmmit, o0)
            newO1 = createLogicalExpressionOmmitingInput(valToOmmit, o1)
            if newO0 is None:
                return newO1
            elif newO1 is None:
                return newO0
            elif o0 is newO0 and o1 is newO1:
                return expr
            elif op == AllOps.AND:
                return expr.obj.netlist.builder.buildAnd(newO0, newO1)
            elif op == AllOps.OR:
                return expr.obj.netlist.builder.buildOr(newO0, newO1)
            else:
                raise NotImplementedError(op, expr)
        elif op == AllOps.NOT:
            o0,  = expr.obj.dependsOn
            newO0 = createLogicalExpressionOmmitingInput(valToOmmit, o0)
            if newO0 is None:
                return None
            elif newO0 is o0:
                return expr
            else:
                return expr.obj.netlist.builder.buildNot(newO0)
        else:
            return expr
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
    assert rw._associatedReadSync is None, (rw, "ReadSync should already have been converted to use of _validNB")
    with dbgTracer.scoped(netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite, n):
        if not isinstance(rw, HlsNetNodeRead) or rw._validNB is None or len(rw.usedBy[syncedDep.out_i]) != 1:
            return modified

        if n.extraCond is None:
            ec = None
        else:
            ec = n.dependsOn[n.extraCond.in_i]

        validNB = rw._validNB
        sw = n.dependsOn[n.skipWhen.in_i]
        if not isinstance(rw, HlsNetNodeRead):
            return modified
        swInNotAndForm = isAndedToNodAndExpr(validNB, sw)
        swInOrNotForm = False
        if not swInNotAndForm:
            swInOrNotForm = isNotOredToOrExpr(validNB, sw)
        if swInNotAndForm or swInOrNotForm:
            # [todo] isAndedToExpression is not sufficient we should that it is not non-trivially reachable
            #        from any term in "and" so we do not create cycle in DAG if we transplant this "and" to an input of n
            r: HlsNetNodeRead = rw
            dbgTracer.log(("Non-blocking associated with read ", r))
            builder: HlsNetlistBuilder = n.netlist.builder

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
            assert n._associatedReadSync is None, (n, "ReadSync should already have been converted to use of _validNB")
            #    reachDb.addAllDepsToOutUseChange(_n)
            #    reachDb.addAllUsersToInDepChange(_n)
            if ec is not None:
                newEc = createLogicalExpressionOmmitingInput(validNB, ec)
                # reachDb.addOutUseChange(ec.obj)
                unlink_hls_nodes(ec, n.extraCond)
                if newEc is not None:
                    r.addControlSerialExtraCond(newEc)
                dbgTracer.log(("update extraCond to", newEc))

            # reachDb.addOutUseChange(sw.obj)
            unlink_hls_nodes(sw, n.skipWhen)
            if swInNotAndForm:
                newSw_n = createLogicalExpressionOmmitingInput(validNB, sw.obj.dependsOn[0])
                if newSw_n is not None:
                    newSw = builder.buildNot(newSw_n)
                    r.addControlSerialSkipWhen(newSw)
                    dbgTracer.log(("update skipWhen to", newSw))
            elif swInOrNotForm:
                newSw = createLogicalExpressionOmmitingInput(builder.buildNot(validNB), sw)
                if newSw is not None:
                    r.addControlSerialSkipWhen(newSw)
                    dbgTracer.log(("update skipWhen to", newSw))
            else:
                raise AssertionError("All cases should be already handled")

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
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)

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
