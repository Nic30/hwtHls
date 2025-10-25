from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.defs import SLICE
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator, OP_INDEX_CONST
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf, \
    getConstOfOutput
from hwt.hdl.types.bits import HBits


def netlistReduceIndexToConstIndex(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    i = getConstOfOutput(n.dependsOn[1])
    if i is not None:
        builder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
        src = n.dependsOn[0]
        if isinstance(i._dtype, HBits):
            i = int(i)
            newOut = builder.buildIndexConst(src, i)
        else:
            i = i.to_py()
            assert i.step == -1, n
            newOut = builder.buildIndexConstSlice(n._outputs[0]._dtype, src, i.start, i.stop)

        replaceOperatorNodeWith(n, newOut, worklist)
        return True
    return False


def netlistReduceIndexSelectAll(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    if n.dependsOn[0]._dtype == n._outputs[0]._dtype:
        replaceOperatorNodeWith(n, n.dependsOn[0], worklist)
        return True
    return False


def netlistReduceIndexOnIndex(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    assert n.operator is OP_INDEX_CONST, n
    srcObj = n.dependsOn[0].obj
    if not isinstance(srcObj, HlsNetNodeOperator):
        return False
    if srcObj.operator is OP_INDEX_CONST:
        # flatten index
        i1 = n.operatorSpecialization
        i0 = srcObj.operatorSpecialization
        newSrc = srcObj.dependsOn[0]
        # flatten newSrc[i0h:i0l][i1h:i1l] -> newSrc[i0l+i1h: i0l+i1l]
        if isinstance(i0, slice) and isinstance(i1, slice):
            assert i0.step == -1, i0
            assert i1.step == -1, i1
            curOut = n._outputs[0]
            offset = i0.stop + i1.stop
            w = i1.start - i1.stop
            assert w > 0, i1
            builder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
            newOut = builder.buildIndexConstSlice(
                curOut._dtype, newSrc,
                offset + w,
                offset)
            replaceOperatorNodeWith(n, newOut, worklist)
            return True

        elif isinstance(i0, slice) and isinstance(i1, int):
            assert i0.step == -1, i0
            curOut = n._outputs[0]
            assert curOut._dtype.bit_length() == 1
            offset = i0.stop + i1
            builder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
            newOut = builder.buildIndexConst(newSrc, offset)
            replaceOperatorNodeWith(n, newOut, worklist)
            return True

    return False
