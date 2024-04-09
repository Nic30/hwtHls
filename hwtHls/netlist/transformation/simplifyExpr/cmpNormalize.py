from typing import Set

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith
from hwtHls.netlist.nodes.const import HlsNetNodeConst

_DENORMALIZED_CMP_OPS = {AllOps.NE, AllOps.UGT, AllOps.UGE, AllOps.SGT, AllOps.SGE}
_NORMALIZED_CMP_OPS = {AllOps.EQ, AllOps.ULT, AllOps.ULE, AllOps.SLT, AllOps.SLE}


def netlistCmpNormalize(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    b: HlsNetlistBuilder = n.netlist.builder
    op = n.operator
    op0, op1 = n.dependsOn
    if op in _NORMALIZED_CMP_OPS:
        return False

    t = n._outputs[0]._dtype
    assert not t.signed, ("Signed should not be used internally")
    #raise NotImplementedError("UGT not correct")
    newO = None
    # :note: const can not be first operand because it denormalizes the expression
    if op is AllOps.NE:
        # a != b -> ~(a == b)
        eq = b.buildOp(AllOps.EQ, t, op0, op1)
        newO = b.buildNot(eq)

    elif op is AllOps.UGT:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a > b -> ~(a <= b)
            le = b.buildOp(AllOps.ULE, t, op0, op1)
            newO = b.buildNot(le)
        else:
            # a > b -> b < a
            newO = b.buildOp(AllOps.ULT, t, op1, op0)

    elif op is AllOps.SGT:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a > b -> ~(a <= b)
            le = b.buildOp(AllOps.SLE, t, op0, op1)
            newO = b.buildNot(le)
        else:
            # a > b -> b < a
            newO = b.buildOp(AllOps.SLT, t, op1, op0)

    elif op is AllOps.UGE:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a >= b -> ~(a < b)
            lt = b.buildOp(AllOps.ULT, t, op0, op1)
            newO = b.buildNot(lt)
        else:
            # a >=- b -> b <= a
            newO = b.buildOp(AllOps.ULE, t, op1, op0)

    elif op is AllOps.SGE:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a >= b -> ~(a < b)
            lt = b.buildOp(AllOps.SLT, t, op0, op1)
            newO = b.buildNot(lt)
        else:
            # a >=- b -> b <= a
            newO = b.buildOp(AllOps.SLE, t, op1, op0)

    if newO is not None:
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    return False
