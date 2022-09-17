from typing import Set, Optional

from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from itertools import islice


def isHlsNetNodeExplicitSyncFlagsRequred(n: HlsNetNodeExplicitSync) -> bool:
    if n.extraCond is not None:
        c = getConstDriverOf(n.extraCond)
        if c is None or int(c) != 1:
            if n.skipWhen is not None:
                c = getConstDriverOf(n.skipWhen)
                if c is not  None and int(c) == 1:
                    # always skipped extraCond does not matter
                    return False
                else:
                    # not always skipped with some extraCond, can not remove
                    return True
            else:
                # not always skipped with some extraCond, can not remove
                return True
    return False

 
def getConstDriverOf(inputObj: HlsNetNodeIn) -> Optional[HValue]:
    dep = inputObj.obj.dependsOn[inputObj.in_i]
    if isinstance(dep.obj, HlsNetNodeConst):
        return dep.obj.val
    else:
        return None


def disconnectAllInputs(n: HlsNetNode, worklist: UniqList[HlsNetNode]):
    for i, dep in zip(n._inputs, n.dependsOn):
        i: HlsNetNodeIn
        dep: HlsNetNodeOut
        # disconnect driver from self
        dep.obj.usedBy[dep.out_i].remove(i)
        worklist.append(dep.obj)


def addAllUsersToWorklist(worklist: UniqList[HlsNetNode], n: HlsNetNodeOperator):
    for uses in n.usedBy:
        for u in uses:
            worklist.append(u.obj)


def replaceOperatorNodeWith(n: HlsNetNodeOperator, newO: HlsNetNodeOut,
                            worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    assert len(n.usedBy) == 1 or all(not uses for uses in islice(n.usedBy, 1, None)), (n, "implemented only for single output nodes or nodes with only first output used")
    builder: HlsNetlistBuilder = n.netlist.builder
    addAllUsersToWorklist(worklist, n)
    builder.replaceOutput(n._outputs[0], newO)
    disconnectAllInputs(n, worklist)
    removed.add(n)
