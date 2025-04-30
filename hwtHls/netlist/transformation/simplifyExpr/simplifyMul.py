from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.code import ctpop
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import getConstDriverOf
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from pyMathBitPrecise.bit_utils import mask, get_bit


def netlistReduceMulConst(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode], maxOnesForRewriteToAddSh:int=3):
    """
    :param maxOnesForRewriteToAddSh: max number of 1 bits in constant for rewrite of mul to add shift
    """
    assert n.operator is HwtOps.MUL, n
    newO = None
    op1 = getConstDriverOf(n._inputs[1])
    if op1 is not None and op1._is_full_valid():
        op0 = n.dependsOn[0]
        builder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
        t = op1._dtype
        assert op1.val >= 0, n

        if op1.val == mask(t.bit_length()):
            # op0 * -1 -> 0 - op0
            newO = builder.buildOp(HwtOps.SUB, None, t, builder.buildConstPy(t, 0), op0, name=n.name)
        elif op1.val == 0:
            # op0 * 0 -> 0
            newO = op1
        elif int(ctpop(op1)) <= maxOnesForRewriteToAddSh:
            # sum shifted op0 for each bit which is 1 in op1
            # op0 * 0b011 -> op0 + (op0 << 1)
            
            # [todo]
            # https://courses.csail.mit.edu/6.111/f2008/handouts/L09.pdf
            # long sequence of 1 may be rewriten to 
            # ...011110... = ...100000... - ...000010... = ...01000 sub(1) 0...
            # op0 * 0b011110 -> (op0 << 5) - (op0 << 1)
            
            op1v = op1.val
            newO = None
            w = t.bit_length()
            for i in range(w):
                op1vLsb = get_bit(op1v, i)
                if op1vLsb:
                    # += op0 << i
                    newOPart = builder.buildShlConst(op0, i)

                    if newO is None:
                        newO = newOPart
                    else:
                        newO = builder.buildOp(HwtOps.ADD, None, t, newO, newOPart, name=n.name)

            assert newO is not None, n
            name = n.name
            if name is not None and len(newO.obj._outputs) == 1 and newO.obj.name is None:
                newO.obj.name = name

            assert newO is not None, n

    if newO is not None:
        replaceOperatorNodeWith(n, newO, worklist)
        return True

    return False
