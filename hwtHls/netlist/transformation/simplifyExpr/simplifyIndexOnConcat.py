from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator, OP_INDEX_CONST
from hwtHls.netlist.transformation.simplifyExpr.simplifyIndexOnMuxOfConcats import sliceOutValueFromConcatOrConst, \
    _buildConcatFromSliceTuples
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def netlistReduceIndexOnConcat(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    assert n.operator == OP_INDEX_CONST, n
    v, = n.dependsOn
    if not (isinstance(v.obj, HlsNetNodeOperator) and v.obj.operator == HwtOps.CONCAT):
        return False
    i = n.operatorSpecialization
    if isinstance(i, int):
        highBitNo = i + 1
        lowBitNo = i
    else:
        assert i.step == -1
        highBitNo = i.start
        lowBitNo = i.stop

    _extracted, _ = sliceOutValueFromConcatOrConst(v, lowBitNo, highBitNo, False)
    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    builder = HlsNetlistBuilderWithWorklist(builder, worklist)
    if _extracted is not None:
        newO = _buildConcatFromSliceTuples(builder, _extracted)
        replaceOperatorNodeWith(n, newO, worklist)
        return True
    return False
