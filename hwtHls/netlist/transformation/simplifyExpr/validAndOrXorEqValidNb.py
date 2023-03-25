from typing import Set

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith


def netlistReduceValidAndOrXorEqValidNb(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    builder: HlsNetlistBuilder = n.netlist.builder
    # search for const in for commutative operator
    o0, o1 = n.dependsOn
    r = o0.obj
    if not isinstance(r, HlsNetNodeRead) or r._valid is None or r._validNB is None:
        # retur because there is not a possibility that this op. is in reducible format
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
    if o is AllOps.AND or o is AllOps.OR:
        replaceOperatorNodeWith(n, r._valid, worklist, removed)
        return True
    elif o is AllOps.XOR:
        replaceOperatorNodeWith(n, builder.buildConstBit(0), worklist, removed)
        return True
    elif o is AllOps.EQ:
        replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist, removed)
        return True
    else:
        raise AssertionError("unsuported operator", n)


