from typing import Set

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


_DENORMALIZED_CMP_OPS = {HwtOps.NE, HwtOps.UGT, HwtOps.UGE, HwtOps.SGT, HwtOps.SGE}
_NORMALIZED_CMP_OPS = {HwtOps.EQ, HwtOps.ULT, HwtOps.ULE, HwtOps.SLT, HwtOps.SLE}


def netlistCmpNormalize(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    b: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    op = n.operator
    op0, op1 = n.dependsOn
    if op in _NORMALIZED_CMP_OPS:
        return False

    t = n._outputs[0]._dtype
    assert not t.signed, ("Signed should not be used internally")
    #raise NotImplementedError("UGT not correct")
    newO = None
    # :note: const can not be first operand because it denormalizes the expression
    if op is HwtOps.NE:
        # a != b -> ~(a == b)
        eq = b.buildOp(HwtOps.EQ, None, t, op0, op1)
        worklist.append(eq.obj)
        newO = b.buildNot(eq)

    elif op is HwtOps.UGT:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a > b -> ~(a <= b)
            le = b.buildOp(HwtOps.ULE, None, t, op0, op1)
            worklist.append(le.obj)
            newO = b.buildNot(le)
        else:
            # a > b -> b < a
            newO = b.buildOp(HwtOps.ULT, None, t, op1, op0)

    elif op is HwtOps.SGT:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a > b -> ~(a <= b)
            le = b.buildOp(HwtOps.SLE, None, t, op0, op1)
            worklist.append(le.obj)
            newO = b.buildNot(le)
        else:
            # a > b -> b < a
            newO = b.buildOp(HwtOps.SLT, None, t, op1, op0)

    elif op is HwtOps.UGE:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a >= b -> ~(a < b)
            lt = b.buildOp(HwtOps.ULT, None, t, op0, op1)
            worklist.append(lt.obj)
            newO = b.buildNot(lt)
        else:
            # a >=- b -> b <= a
            newO = b.buildOp(HwtOps.ULE, None, t, op1, op0)

    elif op is HwtOps.SGE:
        if isinstance(op1.obj, HlsNetNodeConst):
            # a >= b -> ~(a < b)
            lt = b.buildOp(HwtOps.SLT, None, t, op0, op1)
            worklist.append(lt.obj)
            newO = b.buildNot(lt)
        else:
            # a >=- b -> b <= a
            newO = b.buildOp(HwtOps.SLE, None, t, op1, op0)

    if newO is not None:
        worklist.append(newO.obj)
        replaceOperatorNodeWith(n, newO, worklist)
        return True

    return False
