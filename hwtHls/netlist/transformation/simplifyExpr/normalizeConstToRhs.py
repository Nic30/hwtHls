from typing import Set

from hwt.hdl.operatorDefs import COMPARE_OPS, BITWISE_OPS, \
    ALWAYS_COMMUTATIVE_OPS, ALWAYS_ASSOCIATIVE_COMMUTATIVE_OPS, CMP_OP_SWAP
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith

BINARY_OPS_WITH_SWAPABLE_OPERANDS = {*BITWISE_OPS, *COMPARE_OPS, *ALWAYS_COMMUTATIVE_OPS}


def netlistNormalizeConstToRhs(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]) -> bool:
    b: HlsNetlistBuilder = n.netlist.builder
    op = n.operator
    assert op in BINARY_OPS_WITH_SWAPABLE_OPERANDS, "This function should be only called if this is satisfied"
    op0, op1 = n.dependsOn
    if isinstance(op0.obj, HlsNetNodeConst) and not isinstance(op1.obj, HlsNetNodeConst):
        if op in ALWAYS_ASSOCIATIVE_COMMUTATIVE_OPS:
            pass
        else:
            op = CMP_OP_SWAP[op]

        newN = b.buildOp(op, n._outputs[0]._dtype, op1, op0)
        assert newN is not n
        replaceOperatorNodeWith(n, newN, worklist, removed)
        worklist.append(newN.obj)
        return True

    return False
