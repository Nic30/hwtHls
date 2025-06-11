from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import popNotFromExpr, \
    popConstAddFromExpr
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith


def netlistReduceEqNe(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    op = n.operator
    assert op is HwtOps.EQ or op is HwtOps.NE
    o0, o1 = n.dependsOn
    o0n, _, o0 = popNotFromExpr(o0)
    o1n, _, o1 = popNotFromExpr(o1)
    if o0 is o1:
        b = n.getHlsNetlistBuilder()
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

        replaceOperatorNodeWith(n, b.buildConstBit(v), worklist)
        return True

    return False


def netlistReduceCmpConstAfterConstAddSub(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    op = n.operator
    o0, o1 = n.dependsOn
    if isinstance(o1.obj, HlsNetNodeConst):
        o0, op1AddVal = popConstAddFromExpr(o0)
        if op1AddVal is not None:
            b: HlsNetlistBuilder = n.getHlsNetlistBuilder()
            if op is HwtOps.EQ or op is HwtOps.NE:
                # convert to a compare with offset applied
                newO1 = o1.obj.val - op1AddVal
                replacemnt = b.buildOpWithOpt(op, n.operatorSpecialization, n._outputs[0]._dtype, o0, newO1)
                replaceOperatorNodeWith(n, replacemnt, worklist)
                return True
            else:
                # convert to range compare
                if op is HwtOps.ULT:
                    # x + c0 < c1
                    # to
                    # (x < (c1 - c0)) & (x > c0)   is smaller after offset substract, and offset substract does not underflow
                    newO1 = o1.obj.val - op1AddVal
                    cmp = b.buildULt(o0, newO1)
                    underflowCheck = b.buildUGt(o0, op1AddVal)
                    replacemnt = b.buildAnd(cmp, underflowCheck)
                    replaceOperatorNodeWith(n, replacemnt, worklist)
                    # :attention: LLVM automatically normalizes range checks like this back to x + c0 < c1 form
                    return True
                
    return False

