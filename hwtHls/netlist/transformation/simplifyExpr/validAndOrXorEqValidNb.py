
from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def netlistReduceValidAndOrXorEqValidNb(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    # search for const in for commutative operator
    o0, o1 = n.dependsOn
    r = o0.obj
    if not isinstance(r, HlsNetNodeRead) or r._valid is None or r._validNB is None:
        # return because there is not a possibility that this op. is in reducible format
        return False

    if o0 is r._valid:
        if o1 is not r._validNB:
            return False
    elif o0 is r._validNB:
        if o1 is not r._valid:
            return False
    else:
        return False
    # o0 and o1 are r._valid or r._validNB, order does not matter

    o = n.operator
    if o is HwtOps.AND or o is HwtOps.OR:
        replaceOperatorNodeWith(n, r._validNB, worklist)
        return True
    elif o is HwtOps.XOR:
        replaceOperatorNodeWith(n, builder.buildConstBit(0), worklist)
        return True
    elif o is HwtOps.EQ:
        replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist)
        return True
    else:
        raise AssertionError("unsupported operator", n)


