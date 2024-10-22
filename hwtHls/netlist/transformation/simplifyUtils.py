from typing import Optional, Tuple

from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, HlsNetNodeOutAny


def getConstDriverOf(inputObj: Optional[HlsNetNodeIn]) -> Optional[HConst]:
    if inputObj is None:
        return None
    dep = inputObj.obj.dependsOn[inputObj.in_i]
    if isinstance(dep.obj, HlsNetNodeConst):
        return dep.obj.val
    else:
        return None


def getConstOfOutput(o: HlsNetNodeOutAny) -> Optional[HConst]:
    if isinstance(o, HConst):
        return o
    elif isinstance(o, HlsNetNodeOut) and isinstance(o.obj, HlsNetNodeConst):
        return o.obj.val
    else:
        return None


def addAllUsersToWorklist(worklist: SetList[HlsNetNode], n: HlsNetNode):
    for uses in n.usedBy:
        for u in uses:
            worklist.append(u.obj)


def addAllDepsToWorklist(worklist: SetList[HlsNetNode], n: HlsNetNode):
    worklist.extend(dep.obj for dep in n.dependsOn if dep is not None)


def transferHlsNetNodeExplicitSyncOrdering(src: HlsNetNodeExplicitSync, dst: HlsNetNodeExplicitSync):
    currentOrderingDeps = set(dst.dependsOn[i.in_i].obj for i in dst.iterOrderingInputs())
    currentOrderingDeps.add(dst)
    # transfer all ordering inputs from src to dst
    for orderingIn in src.iterOrderingInputs():
        orderingDep = src.dependsOn[orderingIn]
        if orderingDep.obj in currentOrderingDeps:
            continue

        orderingIn.disconnectFromHlsOut(orderingDep)
        # transfer input from sync "n" to "syncedDepObj"
        currentOrderingDeps.add(orderingDep.obj)
        syncedDepObjOI = dst._addInput("orderingIn")
        orderingDep.connectHlsIn(syncedDepObjOI)

    # transfer all ordering uses from ordering port of src to dst
    syncedDepObjOOut = dst.getOrderingOutPort()
    oOut = src.getOrderingOutPort()
    for use in tuple(src.usedBy[oOut.out_i]):
        use: HlsNetNodeIn
        use.disconnectFromHlsOut(oOut)
        if use.obj is dst:
            src._removeInput(use)
            continue

        syncedDepObjOOut.connectHlsIn(use)


def operationTakesMoreThan1Clk(n: HlsNetNodeExplicitSync):
    hadRealization = n.realization is not None
    if not hadRealization:
        n.resolveRealization()
    res = any(n.inputClkTickOffset) or any(n.outputClkTickOffset)
    if not hadRealization:
        n.deleteRealization()
    return res


def isInputConnectedTo(user: Optional[HlsNetNodeIn], dep: Optional[HlsNetNodeOut]) -> bool:
    return dep is None and user is None or\
        dep is not None and user.obj.dependsOn[user.in_i] is dep


def isInputConnectedToOrAndOfIt(dep: Optional[HlsNetNodeOut], userAndMember: Optional[HlsNetNodeOut], user: Optional[HlsNetNodeIn]) -> bool:
    """
    :returns: True if user is driven from dep or userAndMember & dep comutatively
    """
    if dep is None and user is None:
        return True
    if userAndMember is None:
        return dep is not None and user.obj.dependsOn[user.in_i] is dep
    else:
        if user is None:
            return False
        userDep = user.obj.dependsOn[user.in_i]
        if dep is not None and userDep is dep:
            return True
        elif dep is None and userDep is userAndMember:
            return True
        if isinstance(userDep.obj, HlsNetNodeOperator) and userDep.obj.operator == HwtOps.AND:
            o0, o1 = userDep.obj.dependsOn
            if o0 is dep and o1 is userAndMember:
                return True
            elif o1 is userAndMember and o1 is dep:
                return True

        return False


def hasInputSameDriver(i0: Optional[HlsNetNodeIn], i1: Optional[HlsNetNodeIn]) -> bool:
    if i0 is None and i1 is None:
        return True
    elif i0 is not None and i1 is not None:
        return isInputConnectedTo(i0, i1.obj.dependsOn[i1.in_i])
    else:
        return False


def hasInputSameDriverOrAndOfIt(i0: Optional[HlsNetNodeIn], i1AndMember: Optional[HlsNetNodeOut], i1: Optional[HlsNetNodeIn]) -> bool:
    """
    Check that i1 driver = i0 driver or i0 driver | i1AndMember (commutatively)

    :note: simplified version of check that i0 is driven from implication of i1
    """
    if i0 is None and i1 is None:
        return True
    elif i1 is not None:
        i0Dep = None if i0 is None else i0.obj.dependsOn[i0.in_i]
        return isInputConnectedToOrAndOfIt(i0Dep, i1AndMember, i1)
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


def popConstAddFromExpr(e: HlsNetNodeOut):
    addVal = None
    while True:
        obj = e.obj
        if isinstance(obj, HlsNetNodeOperator):
            isCompatible = False

            if obj.operator is HwtOps.ADD:
                isCompatible = True
                isSub = False

            elif obj.operator is HwtOps.SUB:
                isCompatible = True
                isSub = True

            if isCompatible:
                dep0, dep1 = obj.dependsOn
                if isinstance(dep1.obj, HlsNetNodeConst):
                    e = dep0
                    v = dep1.obj.val
                    if isSub:
                        v = -v
                    if addVal is None:
                        addVal = v
                    else:
                        addVal = addVal + v

                    continue

        return e, addVal
