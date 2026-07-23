from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def netlistReduceAddSub(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    op0, op1 = n.dependsOn
    op0: HlsNetNodeOut
    op1: HlsNetNodeOut
    
    builder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
    res = None
    while True:
        if op0 is op1:
            if n.operator == HwtOps.ADD:
                # a + a -> a << 1
                w = op0._dtype.bit_length()
                res = builder.buildConcat(builder.buildConstBit(0), builder.buildIndexConstSlice(HBits(w - 1), op0, w - 1, 0))
                break
            elif n.operator == HwtOps.SUB:
                # a - a -> 0
                res = builder.buildConstPy(op0._dtype, 0)
                break
                
        op1c = getConstDriverOf(n._inputs[1])
        if op1c is not None and op1c._is_full_valid():
            if int(op1c) == 0:
                # a +- 0 -> a
                res = op0
                break
        break

    if res is None:
        return False
    else:
        replaceOperatorNodeWith(n, res, worklist)
        return True
