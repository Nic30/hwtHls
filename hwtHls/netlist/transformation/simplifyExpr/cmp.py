from typing import Set

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import popNotFromExpr, \
    replaceOperatorNodeWith


def netlistReduceEqNe(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
    op = n.operator
    assert op is HwtOps.EQ or op is HwtOps.NE
    o0, o1 = n.dependsOn
    o0n, _, o0 = popNotFromExpr(o0)
    o1n, _, o1 = popNotFromExpr(o1)
    if o0 is o1:
        b = n.netlist.builder
        if op is HwtOps.EQ:
            if o0n == o1n:
                v = 1
            else:
                v = 0
        else:
            if o0n != o1n:
                v = 1
            else:
                v = 0

        replaceOperatorNodeWith(n, b.buildConstBit(v), worklist, removed)
        return True

    return False
