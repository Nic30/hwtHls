from typing import Set, Union

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.sliceConst import HSliceConst
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyExpr.simplifyIndexOnMuxOfConcats import sliceOutValueFromConcatOrConst, \
    sliceOrIndexToHighLowBitNo, _buildConcatFromSliceTuples
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith


def netlistReduceIndexOnConcat(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode],
                               removed: Set[HlsNetNode]):
    v, i = n.dependsOn
    if not (isinstance(v.obj, HlsNetNodeOperator) and v.obj.operator == HwtOps.CONCAT):
        return False

    if not isinstance(i.obj, HlsNetNodeConst):
        return False

    i: Union[HSliceConst, HBitsConst] = i.obj.val

    highBitNo, lowBitNo = sliceOrIndexToHighLowBitNo(i)
    _extracted, _ = sliceOutValueFromConcatOrConst(v, lowBitNo, highBitNo, False)
    builder: HlsNetlistBuilder = n.netlist.builder
    if _extracted is not None:
        newO = _buildConcatFromSliceTuples(builder, worklist, _extracted)
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True
    return False
