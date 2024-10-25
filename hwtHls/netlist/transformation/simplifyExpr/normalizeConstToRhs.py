from hwt.hdl.operatorDefs import COMPARE_OPS, BITWISE_OPS, \
    ALWAYS_COMMUTATIVE_OPS, ALWAYS_ASSOCIATIVE_COMMUTATIVE_OPS, CMP_OP_SWAP
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith

BINARY_OPS_WITH_SWAPABLE_OPERANDS = {*BITWISE_OPS, *COMPARE_OPS, *ALWAYS_COMMUTATIVE_OPS}


def netlistNormalizeConstToRhs(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]) -> bool:
    b: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    op = n.operator
    assert op in BINARY_OPS_WITH_SWAPABLE_OPERANDS, "This function should be only called if this is satisfied"
    op0, op1 = n.dependsOn
    if isinstance(op0.obj, HlsNetNodeConst) and not isinstance(op1.obj, HlsNetNodeConst):
        if op in ALWAYS_ASSOCIATIVE_COMMUTATIVE_OPS:
            pass
        else:
            op = CMP_OP_SWAP[op]

        replacement = b.buildOp(op, n.operatorSpecialization, n._outputs[0]._dtype, op1, op0)
        newN: HlsNetNode = replacement.obj
        assert newN is not n, n
        if n.realization is not None and newN.realization is None:
            newN.assignRealization(n.realization)
            if newN.isMulticlock:
                newN._setScheduleZeroTimeSingleClock(n.scheduledZero)
            else:
                newN._setScheduleZeroTimeSingleClock(n.scheduledZero)
            n.parent._addNodeIntoScheduled(n.scheduledZero // n.netlist.normalizedClkPeriod, newN)

        replaceOperatorNodeWith(n, replacement, worklist)
        worklist.append(replacement.obj)
        return True

    return False
