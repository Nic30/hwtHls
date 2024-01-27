from typing import Set

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith
from hwtHls.netlist.nodes.const import HlsNetNodeConst

_DENORMALIZED_CMP_OPS = {AllOps.NE, AllOps.GT, AllOps.GE}
_NORMALIZED_CMP_OPS = {AllOps.EQ, AllOps.LT, AllOps.LE}


def netlistCmpNormalize(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    b: HlsNetlistBuilder = n.netlist.builder
    op = n.operator
    op0, op1 = n.dependsOn
    if op in _NORMALIZED_CMP_OPS:
        return False

    t = n._outputs[0]._dtype
    if t.signed:
        raise NotImplementedError(n, t)
    
    # :note: const can not be first operand because it denormalizes the expression
    if op is AllOps.NE:
        # a != b -> ~(a == b)
        eq = b.buildOp(AllOps.EQ, t, op0, op1)
        newO = b.buildNot(eq)
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    elif op is AllOps.GT:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a > b -> ~(a <= b)
            le = b.buildOp(AllOps.LE, t, op0, op1)
            newO = b.buildNot(le)
        else:
            # a > b -> b < a
            newO = b.buildOp(AllOps.LT, t, op1, op0)
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    elif op is AllOps.GE:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a >= b -> ~(a < b)
            lt = b.buildOp(AllOps.LT, t, op0, op1)
            newO = b.buildNot(lt)
        else:
            # a >=- b -> b <= a
            newO = b.buildOp(AllOps.LE, t, op1, op0)
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    return False
