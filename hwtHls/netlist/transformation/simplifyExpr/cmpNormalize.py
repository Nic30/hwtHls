from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode
from typing import Set
from hwt.hdl.operatorDefs import AllOps
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith

_DENORMALIZED_CMP_OPS = {AllOps.NE, AllOps.GT, AllOps.GE}
_NORMALIZED_CMP_OPS = {AllOps.EQ, AllOps.LT, AllOps.LE}


def netlistCmpNormalize(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    b: HlsNetlistBuilder = n.netlist.builder
    op = n.operator
    if op in _NORMALIZED_CMP_OPS:
        return False

    t = n._outputs[0]._dtype
    if t.signed:
        raise NotImplementedError(n, t)

    if op is AllOps.NE:
        # a != b -> ~(a == b)
        eq = b.buildOp(AllOps.EQ, t, *n.dependsOn)
        neq = b.buildNot(eq)
        replaceOperatorNodeWith(n, neq, worklist, removed)
        return True

    elif op is AllOps.GT:
        # a > b -> b < a
        lt = b.buildOp(AllOps.LT, t, n.dependsOn[1], n.dependsOn[0])
        replaceOperatorNodeWith(n, lt, worklist, removed)
        return True

    elif op is AllOps.GE:
        le = b.buildOp(AllOps.LE, t, n.dependsOn[1], n.dependsOn[0])
        replaceOperatorNodeWith(n, le, worklist, removed)
        return True

    return False
