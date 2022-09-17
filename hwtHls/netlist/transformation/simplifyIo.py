from itertools import islice
from typing import Set, Generator

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.sliceVal import HSliceVal
from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.connectionsOfStage import extractControlSigOfInterfaceTuple
from hwtHls.netlist.analysis.dataThreads import HlsNetlistAnalysisPassDataThreads
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, unlink_hls_nodes, \
    link_hls_nodes, HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf, \
    replaceOperatorNodeWith, isHlsNetNodeExplicitSyncFlagsRequred


def _collectSyncValidFromExpr(o: HlsNetNodeOut) -> Generator[HlsNetNodeOut, None, None]:
    n = o.obj
    if isinstance(n, HlsNetNodeOperator):
        if isinstance(n, HlsNetNodeMux):
            n: HlsNetNodeMux
            # Check only (cond & val)* | else val
            for v, c in n._iterValueConditionDriverPairs():
                if c is None:
                    yield from _collectSyncValidFromExpr(v)
                else:
                    yield from _collectSyncValidFromExpr(n.netlist.builder.buildAnd(c, v))
        else:
            for dep in n.dependsOn:
                yield from _collectSyncValidFromExpr(dep)

    elif isinstance(n, HlsNetNodeExplicitSync):
        assert o is n._outputs[0], (n, o, "Should read only sync of data")
        sync = n.netlist.builder.buildReadSync(o)
        yield sync

    elif not n._inputs:
        return
    else:
        raise NotImplementedError(o)


def isConnectedToAnyIo(o: HlsNetNodeOut) -> bool:
    n = o.obj
    
    if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeReadSync)):
        return True
    else:
        for dep in n.dependsOn:
            if isConnectedToAnyIo(dep):
                return True
        return False


def netlistReduceReadSync(n: HlsNetNodeReadSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    builder: HlsNetlistBuilder = n.netlist.builder
    # rm this if the source data is constant
    if getConstDriverOf(n._inputs[0]):
        replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
        return True
    # rm this if the source object does not have sync
    dep = n.dependsOn[0].obj
    if isinstance(dep, HlsNetNodeExplicitSync) and dep._associatedReadSync is not n:
        # this readsync is redundant
        replaceOperatorNodeWith(n, dep._associatedReadSync._outputs[0], worklist, removed)
        return True
        
    if isinstance(dep, HlsNetNodeRead):
        dep: HlsNetNodeRead
        vld, _ = extractControlSigOfInterfaceTuple(dep.src)
        if isinstance(vld, (int, BitsVal)):
            assert vld == 1, (dep, vld)
            replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
            return True
        # else:
        #     # try match HlsNetNodeReadNb node if possible
        #     rUses = dep.usedBy[0]
        #     if len(rUses) == 2:
        #         rUse = None
        #         for u in rUses:
        #             if u.obj is not n:
        #                 rUse = u
        #                 break
        #         assert rUse is not None
        #         if rUse.obj.__class__  is HlsNetNodeExplicitSync:
        #             sw = dep.dependsOn[dep.skipWhen.in_i]
        #             if isinstance(sw.obj, HlsNetNodeOperator) and sw.obj.operator is AllOps.NOT and sw.obj.dependsOn[0] is n._outputs[0]:
        #                 raise NotImplementedError("Rewrite as non blocking read")

    elif isinstance(dep, HlsNetNodeWrite):
        _, rd = extractControlSigOfInterfaceTuple(dep.dst)
        if isinstance(rd, (int, BitsVal)):
            assert rd == 1, (dep, vld)
            replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
            return True

    elif not isinstance(dep, HlsNetNodeExplicitSync):
        origDepO = n.dependsOn[0]
        deps = tuple(_collectSyncValidFromExpr(origDepO))
        if not deps:
            newDep = builder.buildConstBit(1)
        elif len(deps) == 1:
            assert deps[0] is not origDepO, (n, origDepO, "If it is same, it must be from some IO and we should not search for it in the first place")
            newDep = deps[0]
        else:
            newDep = builder.buildAndVariadic(deps)
        replaceOperatorNodeWith(n, newDep, worklist, removed)
        return True

    return False


def netlistReduceExplicitSyncConditions(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]): 
    n: HlsNetNodeExplicitSync
    if n.skipWhen is not None:
        dep = n.dependsOn[n.skipWhen.in_i]
        if isinstance(dep.obj, HlsNetNodeConst):
            assert int(dep.obj.val) == 0, ("Constant skipWhen condition must be 0 because otherwise this is should not be used at all", n, dep.obj)
            dep.obj.usedBy[dep.out_i].remove(n.skipWhen)
            worklist.append(dep.obj)
            n._removeInput(n.skipWhen.in_i)
            n.skipWhen = None
        
    if n.extraCond is not None:
        dep = n.dependsOn[n.extraCond.in_i]
        if isinstance(dep.obj, HlsNetNodeConst):
            assert int(dep.obj.val) == 1, ("Constant extraCond must be 1 because otherwise this is should not be used at all", n, dep.obj)
            dep.obj.usedBy[dep.out_i].remove(n.extraCond)
            worklist.append(dep.obj)
            n._removeInput(n.extraCond.in_i)
            n.extraCond = None


def netlistReduceExplicitSync(n: HlsNetNodeExplicitSync, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    syncDep: HlsNetNodeOut = n.dependsOn[0]
    
    if not n.usedBy[0]:
        # remove whole node if not synchronizing anything
        if isHlsNetNodeExplicitSyncFlagsRequred(n):
            return False
        for i in n._inputs:
            dep = n.dependsOn[i.in_i]
            dep.obj.usedBy[dep.out_i].remove(i)
            worklist.append(dep.obj)
        
        removed.add(n)

    elif getConstDriverOf(n._inputs[0]) is not None and all(not use for use in islice(n.usedBy, 1, None)):
        # input is constant and ordering is not used
        for _ in range(len(n.usedBy) - 1):
            n.usedBy.pop()
            n._outputs.pop()
        if n._associatedReadSync is not None:
            raise NotImplementedError(n)

        replaceOperatorNodeWith(n, syncDep, worklist, removed)
        return True

    elif (n.skipWhen is None or getConstDriverOf(n.skipWhen) is not None) and (
            n.extraCond is None or getConstDriverOf(n.extraCond) is not None):
        # synchronization node without any synchronization flag specified
        assert n.skipWhen is None or n.dependsOn[n.skipWhen.in_i].obj.val == 0, n
        assert n.extraCond is None or n.dependsOn[n.extraCond.in_i].obj.val == 1, n
        
        _, orderingOutUses = n._outputs.pop(), n.usedBy.pop()
        if orderingOutUses:
            for orderingIn in n.iterOrderingInputs():
                orderingDep = n.dependsOn[orderingIn.in_i]
                for u in orderingOutUses:
                    u: HlsNetNodeIn
                    u.replaceDriverInInputOnly(orderingDep)
             
        replaceOperatorNodeWith(n, syncDep, worklist, removed)
        return True

    elif (n.extraCond is not None and
          n.skipWhen is not None and
          isinstance(syncDep.obj, HlsNetNodeRead)):
        # try extract non blocking read
        r: HlsNetNodeRead = syncDep.obj
        # 2 usedBy for _associatedReadSync and this node "n" 
        if  r._associatedReadSync is None or not r._isBlocking or len(r.usedBy[0]) > 2:
            return False
        if netlistReduceReadSync(r._associatedReadSync, worklist, removed):
            return True

        vld = r._associatedReadSync._outputs[0]
        ec = n.dependsOn[n.extraCond.in_i]
        sw = n.dependsOn[n.skipWhen.in_i]
        if (ec is vld and
                isinstance(sw.obj, HlsNetNodeOperator) and
                sw.obj.operator is AllOps.NOT and
                sw.obj.dependsOn[0] is vld):
            # Try extracting non-blocking read from pattern:
            # x = read()
            # x.explicitSync(extraCond=x.valid, skipWhen=~x.valid)
            
            # ec == vld
            # sw == ~vld
            # replace vld in ec/sw expression with 1 only only for this "n"
            # if used anywhere else replace with r.valid,
            # transfer ec/sw from this "n" to parent read "r"
            dataUses = tuple(n.usedBy[0])
            data = n._outputs[0]
            if n._associatedReadSync:
                raise NotImplementedError()

            unlink_hls_nodes(ec, n.extraCond)
            unlink_hls_nodes(sw, n.skipWhen)
            vldUses = tuple(r._associatedReadSync.usedBy[0])
            vld = r._associatedReadSync._outputs[0]

            for u in vldUses:
                unlink_hls_nodes(vld, u)

            for u in dataUses:
                unlink_hls_nodes(data, u)

            unlink_hls_nodes(r._outputs[0], n._inputs[0])
            
            r.setNonBlocking()
            data = r._outputs[0]
            vld = r._valid
            for u in vldUses:
                link_hls_nodes(vld, u)
                worklist.append(u.obj)

            for u in dataUses:
                if u.obj is r._associatedReadSync or u.obj is n:
                    continue
                link_hls_nodes(data, u)
                worklist.append(u.obj)
            
            removed.add(n)

            unlink_hls_nodes(r._outputs[0], r._associatedReadSync._inputs[0])
            removed.add(r._associatedReadSync)
            r._associatedReadSync = None
            
            netlistReduceExplicitSyncConditions(r, worklist, removed)
            
            return True
        # elif (isinstance(syncDep.obj, HlsNetNodeOperator) and
        #      syncDep.obj.operator is AllOps.AND and
        #      (syncDep.dependsOn == (r._outputs[0], vld) or 
        #       syncDep.dependsOn == (vld, r._outputs[0]))):
        #    # r = read()
        #    # r0 = r.data & r.valid
        #    # n = r0.explicitSync()
    elif not isConnectedToAnyIo(syncDep):
        # not synchronizing anything because there is no IO involved in input
        assert len(n._outputs) == 2, n
        
        # transfer all ordering inputs from "n" to all users
        oo = n.getOrderingOutPort()
        assert oo.out_i == 1
        orderingDeps = tuple(n.dependsOn[oi.in_i] for oi in n.iterOrderingInputs())
        for u in tuple(n.usedBy[oo.out_i]):
            unlink_hls_nodes(oo, u)
            # and add dependencies from depObj to orderingI.obj
            uObj: HlsNetNodeExplicitSync = u.obj
            userOrderingDeps = set(uObj.dependsOn[uoi.in_i] for uoi in u.iterOrderingInputs())
            for oi in orderingDeps:
                oi: HlsNetNodeOut
                if oi in userOrderingDeps:
                    continue
                else:
                    userOrderingDeps.add(oi)
                    uoi = uObj._addInput("orderingIn")
                    link_hls_nodes(oi, uoi)
    
        replaceOperatorNodeWith(n, syncDep, worklist, removed)
        return True

    return False


def netlistReduceExplicitSyncOrdering(n: HlsNetNodeExplicitSync, threads: HlsNetlistAnalysisPassDataThreads):
    # remove ordering if it is redundant information
    for orderingI in tuple(n.iterOrderingInputs()):
        orderingI: HlsNetNodeIn
        t0 = threads.threadPerNode.get(n, None)
        if t0 is None:
            continue
        dep = n.dependsOn[orderingI.in_i]
        depObj: HlsNetNodeExplicitSync = dep.obj
        t1 = threads.threadPerNode.get(depObj, None)
        if t1 is None:
            continue
        if t0 is t1:
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
                continue

            # rm dep -> orderingI
            depObj.usedBy[dep.out_i].remove(orderingI)
            n._removeInput(orderingI.in_i)
            nOrderingUses: Set[HlsNetNodeExplicitSync] = set()
            for oi in n.iterOrderingInputs():
                nOrderingUses.add(n.dependsOn[oi.in_i].obj)

            # and add dependencies from depObj to orderingI.obj
            for oi in depObj.iterOrderingInputs():
                oi: HlsNetNodeIn
                depDep = depObj.dependsOn[oi.in_i]
                
                if depDep.obj in nOrderingUses:
                    continue
                else:
                    nOrderingUses.add(depDep.obj)
                    nOi = n._addInput("orderingIn")
                    link_hls_nodes(depDep, nOi)

            # and add uses from orderingI.obj to depObj
            oo = n.getOrderingOutPort()
            depOo = depObj.getOrderingOutPort()
            depOrderingUses: Set[HlsNetNodeExplicitSync] = set()
            for u in depObj.usedBy[depOo.out_i]:
                depOrderingUses.add(u.obj)

            for u in n.usedBy[oo.out_i]:
                u: HlsNetNodeIn
                if u.obj in depOrderingUses:
                    continue
                else:
                    depOrderingUses.add(u.obj)
                    i = u.obj._addInput("orderingIn")
                    link_hls_nodes(depOo, i)


def netlistReduceReadNonBlocking(n: HlsNetNodeRead, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    
    # try convert uses of "rawValue" to uses of "dataOut" and "valid" outputs
    rawValueO: HlsNetNodeOut = n._rawValue
    rawUses = n.usedBy[rawValueO.out_i]
    dataWidth = n._outputs[0]._dtype.bit_length()
    for u in rawUses:
        u: HlsNetNodeIn
        uObj: HlsNetNode = u.obj
        if isinstance(uObj, HlsNetNodeOperator) and uObj.operator == AllOps.INDEX and rawValueO is uObj.dependsOn[0]:
            i = getConstDriverOf(uObj._inputs[1])
            if i is not None:
                iVal = i.val
                if isinstance(iVal, (BitsVal, int)):
                    iVal = int(iVal)
                    if iVal == dataWidth:
                        replaceOperatorNodeWith(uObj, n._valid, worklist, removed)
                        return True
                    elif iVal == 0 and dataWidth == 1:
                        replaceOperatorNodeWith(uObj, n._outputs[0], worklist, removed)
                        return True
                    else:
                        raise NotImplementedError("Index in data segment")
                else:
                    assert isinstance(iVal, HSliceVal), iVal
                    assert iVal.step == -1, iVal
                    highBitNo = int(iVal.start)
                    lowBitNo = int(iVal.stop)
                    if lowBitNo == 0 and highBitNo == dataWidth:
                        replaceOperatorNodeWith(uObj, n._outputs[0], worklist, removed)
                        return True
                    else:
                        raise NotImplementedError("Index in data segment")    
    
