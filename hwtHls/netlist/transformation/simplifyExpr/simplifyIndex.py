from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.defs import SLICE
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def netlistReduceIndexOnIndex(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    assert n.operator is HwtOps.INDEX, n
    srcObj = n.dependsOn[0].obj
    indxObj = n.dependsOn[1].obj
    if (isinstance(indxObj, HlsNetNodeConst) and
        isinstance(srcObj, HlsNetNodeOperator) and
        srcObj.operator is HwtOps.INDEX and
        isinstance(srcObj.dependsOn[1].obj, HlsNetNodeConst)):
        # flatten index
        i1 = indxObj.val
        i0 = srcObj.dependsOn[1].obj.val
        newSrc = srcObj.dependsOn[0]
        # flatten newSrc[i0h:i0l][i1h:i1l] -> newSrc[i0l+i1h: i0l+i1l]
        if i0._dtype == i1._dtype:
            if i0._dtype == SLICE:
                i0 = i0.to_py()
                i1 = i1.to_py()
                assert i0.step == -1, i0
                assert i1.step == -1, i1
                curOut = n._outputs[0]
                offset = i0.stop + i1.stop
                w = i1.start - i1.stop
                assert w > 0, i1
                newOut = n.getHlsNetlistBuilder().buildIndexConstSlice(
                    curOut._dtype, newSrc,
                    offset + w,
                    offset,
                    worklist)
                replaceOperatorNodeWith(n, newOut, worklist)

                return True

    return False
