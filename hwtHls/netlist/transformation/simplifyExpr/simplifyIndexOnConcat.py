from typing import Set, Union

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.sliceVal import HSliceVal
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyExpr.sliceOnMuxOfConcats import sliceOutValueFromConcatOrConst, \
    sliceOrIndexToHighLowBitNo, _buildConcatFromSliceTuples
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith


def netlistReduceIndexOnConcat(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode],
                               removed: Set[HlsNetNode]):
    v, i = n.dependsOn
    if not (isinstance(v.obj, HlsNetNodeOperator) and v.obj.operator == AllOps.CONCAT):
        return False

    if not isinstance(i.obj, HlsNetNodeConst):
        return False

    i: Union[HSliceVal, BitsVal] = i.obj.val

    highBitNo, lowBitNo = sliceOrIndexToHighLowBitNo(i)
    _extracted, _ = sliceOutValueFromConcatOrConst(v, lowBitNo, highBitNo, False)
    builder: HlsNetlistBuilder = n.netlist.builder
    if _extracted is not None:
        newO = _buildConcatFromSliceTuples(builder, worklist, _extracted)
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True
    return False
