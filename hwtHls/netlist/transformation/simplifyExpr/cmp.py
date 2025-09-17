from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder,\
    HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.transformation.simplifyUtils import popNotFromExpr, \
    popConstAddFromExpr
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from pyMathBitPrecise.bit_utils import mask


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


def offsetAndSizeToRanges(offset: HBitsConst, size: HBitsConst):
    """
    :see: original c++ code in ICmpToOnlyEqLtLePass
    """

    # x + c0 < c1  ; c1 is range size; c0 is range offset
    #  < c1 selects the range <0, c0)
    #  + c0 shifts this range to <0-c0, -c0+c1) however the range may wrap around max or min val c0, c1
    #  For the left side of the selected range:
    if not size:
        # unsigned x + c0 < 0 selects an empty interval
        return
    t = size._dtype
    w = t.bit_length()
    cMin = t.from_py(0)
    cMax = t.from_py(mask(w))

    if size._eq(cMax):
        # The range covers the entire space
        yield (cMin, cMax)
    else:
        low = -offset
        high = -offset + size
        if high > low:
            # No wrap around
            yield (low, high - 1)
        else:
            # Wrap around case, from start to cMax and from cMin to high
            yield (cMin, high - 1)
            yield (low, cMax)


def CreateRangeCheck(Builder: HlsNetlistBuilder, x, low: HBitsConst, high: HBitsConst):
    """
    :see: original c++ code in ICmpToOnlyEqLtLePass
    """
    res = None
    if not low._eq(0):
        # res = Builder.CreateICmpUGE(x, low)
        # a >= b -> ~(a < b)  (to keep normal form of ICmpToOnlyEqLtLePass)
        lt = Builder.buildULt(x, Builder.buildConst(low))
        res = Builder.buildNot(lt)

    if not high._eq(mask(high._dtype.bit_length())):
        highP1 = high + 1
        lt = Builder.buildULt(x, Builder.buildConst(highP1))
        if res is not None:
            res = Builder.buildAnd(res, lt)
        else:
            res = lt
    if res is None:
        return Builder.buildConstBit(1)

    return res


def netlistReduceCmpConstAfterConstAddSub(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    op = n.operator
    o0, o1 = n.dependsOn
    if isinstance(o1.obj, HlsNetNodeConst):
        o0, op1AddVal = popConstAddFromExpr(o0)
        if op1AddVal is not None:
            b: HlsNetlistBuilder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
            if op is HwtOps.EQ or op is HwtOps.NE:
                # convert to a compare with offset applied
                newO1 = o1.obj.val - op1AddVal
                replacement = b.buildOpWithOpt(op, n.operatorSpecialization, n._outputs[0]._dtype, o0, newO1)
                replaceOperatorNodeWith(n, replacement, worklist)
                return True
            else:
                # convert to range compare
                # :attention: LLVM automatically normalizes range checks like this back to x + c0 < c1 form
                # :note: based on ICmpToOnlyEqLtLePass::_tryRewriteRangeCheckTo2xCmp
                if op is HwtOps.ULT:
                    x = o0
                    offset = op1AddVal
                    size = o1.obj.val
                    ranges = tuple(offsetAndSizeToRanges(offset, size))
                    if not ranges:
                        replacement = b.buildConstBit(0)
                    else:
                        replacement = None
                        for r in ranges:
                            rCmp = CreateRangeCheck(b, x, r[0], r[1])
                            if replacement is not None:
                                replacement = b.buildOr(replacement, rCmp)
                            else:
                                replacement = rCmp

                    replaceOperatorNodeWith(n, replacement, worklist)
                    return True

    return False


if __name__ == "__main__":
    from hwt.hdl.types.bits import HBits
    t = HBits(3)
    offset = 5
    size = 6
    ranges = ((0, 0), (3, 7))
    for i in range(int(2 ** 3)):
        isIn0 = t.from_py(i) + t.from_py(offset) < t.from_py(size)
        isIn1 = False
        for r in ranges:
            if i >= r[0] and i <= r[1]:
                isIn1 = True
                break
        assert isIn0 == isIn1, (i, isIn0, isIn1)
        # print(i, int(isIn0), int(isIn1))
