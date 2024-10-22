from typing import Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import netlistExplicitSyncDisconnectFromOrderingChain


def netlistReduceExplicitSyncFlags(dbgTracer: DebugTracer, n: HlsNetNodeExplicitSync,
                                   worklist: Optional[SetList[HlsNetNode]]):
    """
    Remove skipWhen extraCond ports if they are useless and remove n if it has no sync flags and is directly HlsNetNodeExplicitSync instance.
    """
    with dbgTracer.scoped(netlistReduceExplicitSyncFlags, n):
        modified = False
        if n.skipWhen is not None:
            dep = n.dependsOn[n.skipWhen.in_i]
            if isinstance(dep.obj, HlsNetNodeConst):
                if int(dep.obj.val) == 0:
                    # ("Constant skipWhen condition must be 0, because otherwise the channel is always skipped", n, dep.obj)
                    n.skipWhen.disconnectFromHlsOut(dep)
                    if worklist is not None:
                        worklist.append(dep.obj)
                        worklist.append(n)
                    n._removeInput(n.skipWhen.in_i)
                    modified = True
                    dbgTracer.log("rm skipWhen")

        if n.extraCond is not None:
            dep = n.dependsOn[n.extraCond.in_i]
            if (isinstance(dep.obj, HlsNetNodeConst) and int(dep.obj.val) == 1) or n._validNB is not None and dep is n._validNB:
                # ("Constant extraCond must be 1, because otherwise the channel is always blocked", n, dep.obj)
                n.extraCond.disconnectFromHlsOut(dep)
                if worklist is not None:
                    worklist.append(dep.obj)
                    worklist.append(n)
                n._removeInput(n.extraCond.in_i)
                modified = True
                dbgTracer.log("rm extraCond")

        b: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        if not n._rtlUseValid:
            for vld in (n._valid, n._validNB):
                if vld is not None:
                    b.replaceOutputWithConst1b(vld, True)

        if not n._rtlUseReady:
            for rd in (n._ready, n._readyNB):
                if rd is not None:
                    b.replaceOutputWithConst1b(rd, True)

        for outFlag in (n._valid, n._validNB, n._ready, n._readyNB, getattr(n, "_rawValue", None)):
            if outFlag is not None and not n.usedBy[outFlag.out_i]:
                n._removeOutput(outFlag.out_i)

        return modified


def removeSyncReadOfRead(r: HlsNetNodeRead):
    r._associatedReadSync._inputs[0].disconnectFromHlsOut(r._portDataOut)
    r._associatedReadSync.markAsRemoved()
    r._associatedReadSync = None


def isAndedToExpression(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    """
    Check if expression is in format expr = And(.., valToSearch, ...)
    """
    if expr is valToSearch:
        return True
    elif isinstance(expr.obj, HlsNetNodeOperator) and expr.obj.operator == HwtOps.AND:
        for o in expr.obj.dependsOn:
            if isAndedToExpression(valToSearch, o):
                return True

    return False


def isAndedToNotAndExpr(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    """
    Check if expression is in format expr = ~And(.., valToSearch, ...)
    """
    return isinstance(expr.obj, HlsNetNodeOperator) and \
           expr.obj.operator is HwtOps.NOT and \
           isAndedToExpression(valToSearch, expr.obj.dependsOn[0])


def isNot(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    return isinstance(expr.obj, HlsNetNodeOperator) and \
           expr.obj.operator is HwtOps.NOT and \
           expr.obj.dependsOn[0] is valToSearch


def isNotOredToOrExpr(valToSearch: HlsNetNodeOut, expr: HlsNetNodeOut):
    """
    Check if expression is in format expr = Or(.., ~valToSearch, ...)
    """
    if isNot(valToSearch, expr):
        return True
    elif isinstance(expr.obj, HlsNetNodeOperator) and expr.obj.operator == HwtOps.OR:
        for o in expr.obj.dependsOn:
            if isNotOredToOrExpr(valToSearch, o):
                return True

    return False


def createLogicalExpressionOmmitingInput(valToOmmit: HlsNetNodeOut, expr: HlsNetNodeOut):
    if expr is valToOmmit:
        return None
    elif isinstance(expr.obj, HlsNetNodeOperator):
        op = expr.obj.operator
        if op == HwtOps.AND or op == HwtOps.OR:
            o0, o1 = expr.obj.dependsOn
            newO0 = createLogicalExpressionOmmitingInput(valToOmmit, o0)
            newO1 = createLogicalExpressionOmmitingInput(valToOmmit, o1)
            if newO0 is None:
                return newO1
            elif newO1 is None:
                return newO0
            elif o0 is newO0 and o1 is newO1:
                return expr
            elif op == HwtOps.AND:
                return expr.obj.getHlsNetlistBuilder().buildAnd(newO0, newO1)
            elif op == HwtOps.OR:
                return expr.obj.getHlsNetlistBuilder().buildOr(newO0, newO1)
            else:
                raise NotImplementedError(op, expr)
        elif op == HwtOps.NOT:
            o0, = expr.obj.dependsOn
            newO0 = createLogicalExpressionOmmitingInput(valToOmmit, o0)
            if newO0 is None:
                return None
            elif newO0 is o0:
                return expr
            else:
                return expr.obj.getHlsNetlistBuilder().buildNot(newO0)
        else:
            return expr
    else:
        return expr


def netlistReduceExplicitSyncTryExtractNonBlockingReadOrWrite(dbgTracer: DebugTracer,
                                                              n: HlsNetNodeExplicitSync,
                                                              worklist: SetList[HlsNetNode]):
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
        swInNotAndForm = isAndedToNotAndExpr(validNB, sw)
        swInOrNotForm = False
        if not swInNotAndForm:
            swInOrNotForm = isNotOredToOrExpr(validNB, sw)
        if swInNotAndForm or swInOrNotForm:
            # [todo] isAndedToExpression is not sufficient we should that it is not non-trivially reachable
            #        from any term in "and" so we do not create cycle in DAG if we transplant this "and" to an input of n
            r: HlsNetNodeRead = rw
            dbgTracer.log(("Non-blocking associated with read ", r))
            builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()

            # Try extracting non-blocking read from pattern:
            # x = read()
            # x.explicitSync(extraCond=x.valid, skipWhen=~x.valid)

            # ec == validNB
            # sw == ~validNB
            # replace validNB in ec/sw expression with 1 only only for this "n"
            # if used anywhere else replace with r.valid,
            # transfer ec/sw from this "n" to parent read "r"
            dataUses = tuple(n.usedBy[n._portDataOut.out_i])
            data = n._portDataOut
            assert n._associatedReadSync is None, (n, "ReadSync should already have been converted to use of _validNB")
            #    reachDb.addAllDepsToOutUseChange(_n)
            #    reachDb.addAllUsersToInDepChange(_n)
            if ec is not None:
                newEc = createLogicalExpressionOmmitingInput(validNB, ec)
                # reachDb.addOutUseChange(ec.obj)
                n.extraCond.disconnectFromHlsOut(ec)
                if newEc is not None:
                    r.addControlSerialExtraCond(newEc)
                dbgTracer.log(("update extraCond to", newEc))

            # reachDb.addOutUseChange(sw.obj)
            n.skipWhen.disconnectFromHlsOut(sw)
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
            #    u.disconnectFromHlsOut(vld)

            # reachDb.addOutUseChange(n)
            for u in dataUses:
                # reachDb.addInDepChange(u.obj)
                u.disconnectFromHlsOut(data)

            # reachDb.addOutUseChange(r)
            n._inputs[0].disconnectFromHlsOut(n.dependsOn[0])
            netlistExplicitSyncDisconnectFromOrderingChain(dbgTracer, n, worklist)

            r.setNonBlocking()
            data = syncedDep
            # vld = r._valid
            # for u in vldUses:
            #    u.disconnectFromHlsOut(vld)
            #    worklist.append(u.obj)

            for u in dataUses:
                data.connectHlsIn(u)
                worklist.append(u.obj)

            n.markAsRemoved()
            dbgTracer.log("rm")
            netlistReduceExplicitSyncFlags(dbgTracer, r, worklist)
            return True

        # elif (isinstance(syncedDep.obj, HlsNetNodeOperator) and
        #      syncedDep.obj.operator is HwtOps.AND and
        #      (syncedDep.dependsOn == (r._portDataOut, vld) or
        #       syncedDep.dependsOn == (vld, r._portDataOut))):
        #    # r = read()
        #    # r0 = r.data & r.valid
        #    # n = r0.explicitSync()
        return modified


def tryExtractNonBlockingVoidRead(n: HlsNetNodeRead, readSync:HlsNetNodeReadSync,
                                  worklist: SetList[HlsNetNode]):
    assert readSync is n._associatedReadSync, (n, n._associatedReadSync, readSync)
    if len(n.usedBy[0]) == 1 and n.extraCond is None and n.skipWhen is None:
        n.setNonBlocking()
        n.getHlsNetlistBuilder().replaceOutput(readSync._outputs[0], n._valid, True)
        removeSyncReadOfRead(n)
        worklist.extend(u.obj for u in n.usedBy[n._valid.out_i])
        return True

    return False
