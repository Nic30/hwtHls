from itertools import islice
from typing import Set, Optional, Tuple

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, \
    unlink_hls_nodes, link_hls_nodes, HlsNetNodeOutAny


def getConstDriverOf(inputObj: Optional[HlsNetNodeIn]) -> Optional[HConst]:
    if inputObj is None:
        return None
    dep = inputObj.obj.dependsOn[inputObj.in_i]
    if isinstance(dep.obj, HlsNetNodeConst):
        return dep.obj.val
    else:
        return None


def getConstOfOutput(o: HlsNetNodeOutAny) -> Optional[HConst]:
    if isinstance(o, HlsNetNodeOut) and isinstance(o.obj, HlsNetNodeConst):
        return o.obj.val
    else:
        return None


def disconnectAllInputs(n: HlsNetNode, worklist: SetList[HlsNetNode]):
    for i, dep in zip(n._inputs, n.dependsOn):
        i: HlsNetNodeIn
        dep: HlsNetNodeOut
        # disconnect driver from self
        dep.obj.usedBy[dep.out_i].remove(i)
        worklist.append(dep.obj)
        n.dependsOn[i.in_i] = None

    if isinstance(n, HlsNetNodeAggregatePortIn):
        i: HlsNetNodeIn = n.parentIn
        dep: HlsNetNodeOut = i.obj.dependsOn[i.in_i]
        # disconnect driver from self
        dep.obj.usedBy[dep.out_i].remove(i)
        worklist.append(dep.obj)
        i.obj.dependsOn[i.in_i] = None


def addAllUsersToWorklist(worklist: SetList[HlsNetNode], n: HlsNetNode):
    for uses in n.usedBy:
        for u in uses:
            worklist.append(u.obj)


def replaceOperatorNodeWith(n: HlsNetNodeOperator, newO: HlsNetNodeOut,
                            worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
    assert len(n.usedBy) == 1 or all(not uses for uses in islice(n.usedBy, 1, None)), (
        n, "implemented only for single output nodes or nodes with only first output used")
    assert newO.obj not in removed, newO
    oldTy = n._outputs[0]._dtype
    newTy = newO._dtype
    assert oldTy == newO._dtype or (isinstance(oldTy, HBits) and
                                    isinstance(newTy, HBits) and oldTy.bit_length() == newTy.bit_length()), (oldTy, newO._dtype)
    builder: "HlsNetlistBuilder" = n.netlist.builder
    addAllUsersToWorklist(worklist, n)

    # add dependencies which do not have any other use to worklist
    for dep in n.dependsOn:
        hasAnyOtherUser = False
        for u in dep.obj.usedBy[dep.out_i]:
            if u.obj is not n:
                hasAnyOtherUser = True
                break
        if not hasAnyOtherUser:
            worklist.append(dep.obj)

    builder.replaceOutput(n._outputs[0], newO, True)
    disconnectAllInputs(n, worklist)
    removed.add(n)


def transferHlsNetNodeExplicitSyncOrdering(src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync):
    currentOrderingDeps = set(dst.dependsOn[i.in_i].obj for i in dst.iterOrderingInputs())
    currentOrderingDeps.add(dst)
    # transfer all ordering inputs from src to dst
    for orderingIn in src.iterOrderingInputs():
        orderingDep = src.dependsOn[orderingIn]
        if orderingDep.obj in currentOrderingDeps:
            continue

        unlink_hls_nodes(orderingDep, orderingIn)
        # transfer input from sync "n" to "syncedDepObj"
        currentOrderingDeps.add(orderingDep.obj)
        syncedDepObjOI = dst._addInput("orderingIn")
        link_hls_nodes(orderingDep, syncedDepObjOI)

    # transfer all ordering uses from ordering port of src to dst
    syncedDepObjOOut = dst.getOrderingOutPort()
    oOut = src.getOrderingOutPort()
    for use in tuple(src.usedBy[oOut.out_i]):
        use: HlsNetNodeIn
        unlink_hls_nodes(oOut, use)
        if use.obj is dst:
            src._removeInput(use)
            continue

        link_hls_nodes(syncedDepObjOOut, use)


def operationTakesMoreThan1Clk(n: HlsNetNodeExplicitSync):
    hadRealization = n.realization is not None
    if not hadRealization:
        n.resolveRealization()
    res = any(n.inputClkTickOffset) or any(n.outputClkTickOffset)
    if not hadRealization:
        n.deleteRealization()
    return res


def isInputConnectedTo(user: Optional[HlsNetNodeIn], dep: Optional[HlsNetNodeOut]) -> bool:
    return dep is None and user is None or dep is not None and user.obj.dependsOn[user.in_i] is dep


def hasInputSameDriver(i0: Optional[HlsNetNodeIn], i1: Optional[HlsNetNodeIn]) -> bool:
    if i0 is None and i1 is None:
        return True
    elif i0 is not None and i1 is not None:
        return isInputConnectedTo(i0, i1.obj.dependsOn[i1.in_i])
    else:
        return False


def iterOperatorTreeInputs(root: HlsNetNodeOut, ops: Tuple[HOperatorDef]):
    """
    :note: The most left input first
    """
    for dep in root.dependsOn:
        depO = dep.obj
        if isinstance(depO, HlsNetNodeOperator) and depO.operator is ops:
            yield from iterOperatorTreeInputs(depO, ops)
        else:
            yield dep


def popNotFromExpr(e: HlsNetNodeOut):
    negated = False
    while True:
        obj = e.obj
        if isinstance(obj, HlsNetNodeOperator) and obj.operator is HwtOps.NOT:
            negated = not negated
            e = obj.dependsOn[0]
        else:
            return negated, obj, e

