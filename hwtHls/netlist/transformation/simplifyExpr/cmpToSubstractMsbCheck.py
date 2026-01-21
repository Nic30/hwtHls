from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder, \
    HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith
from pyMathBitPrecise.bit_utils import mask, to_signed, to_unsigned


# https://lumetta.web.engr.illinois.edu/120-S19/slide-copies/053-2's-complement-comparator.pdf
# def _icmp_slt(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
#     widthP1 = a._dtype.bit_length() + 1
#     a = builder.buildZExt(a, widthP1)
#     b = builder.buildZExt(b, widthP1)
#     diff = builder.buildSub(a, b)
#     diffMsb = builder.buildIndexConst(diff, widthP1 - 1)
#     carryOut = builder.buildGetMsb(diff)
#     slt = builder.buildXor(builder.buildNot(carryOut), diffMsb)
#     return  slt
# def _icmp_slt(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
#     widthP1 = a._dtype.bit_length() + 1
#     a = builder.buildSExt(a, widthP1)
#     b = builder.buildSExt(b, widthP1)
#     diff = builder.buildSub(a, b)
#     return builder.buildGetMsb(diff)
def _icmp_slt(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    width = a._dtype.bit_length()

    a_sign = builder.buildIndexConst(a, width - 1)
    b_sign = builder.buildIndexConst(b, width - 1)

    # Compute a - b in original width (two's complement wrap is fine here)
    diff = builder.buildSub(a, b)
    diff_sign = builder.buildIndexConst(diff, width - 1)

    # sa ^ sb
    sa_xor_sb = builder.buildXor(a_sign, b_sign)
    same_sign = builder.buildNot(sa_xor_sb)  # ~(sa ^ sb)

    # Case 1: sa & ~sb (negative < positive)
    neg_lt_pos = builder.buildAnd(a_sign, builder.buildNot(b_sign))

    # Case 2: same sign, use sign(diff)
    same_sign_and_diff = builder.buildAnd(same_sign, diff_sign)

    # slt = (sa & ~sb) | (~(sa ^ sb) & sd)
    slt = builder.buildOr(neg_lt_pos, same_sign_and_diff)
    return slt


def _icmp_sgt(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    return _icmp_slt(builder, b, a)  # Symmetry


def _icmp_sle(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    return builder.buildNot(_icmp_sgt(builder, a, b))  # Or !(a - b)[width-1]


def _icmp_sge(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    return builder.buildNot(_icmp_slt(builder, a, b))


def _icmp_ult(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    widthP1 = a._dtype.bit_length() + 1
    a_ext = builder.buildZExt(a, widthP1)
    b_ext = builder.buildZExt(b, widthP1)
    diff = builder.buildSub(a_ext, b_ext)  # No wrap in extra bit
    carryOut = builder.buildGetMsb(diff)
    return carryOut  # Carry-out bit (MSB of extended)
#
#def _icmp_ult(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
#
#    # diff = a - b (wrap is fine: we will not use its sign as the result)
#    diff = builder.buildSub(a, b)
#
#    # Compute (a ^ b): bits that differ
#    axorb = builder.buildXor(a, b)
#
#    # Find the highest differing bit: mask = msb_one_hot(axorb)
#    # For arbitrary bitwidth and only bit operations available,
#    # you can build a priority-OR tree, but conceptually:
#    #   mask has exactly that highest differing bit = 1
#    # Then:
#    #   a_lt_b = ((~a) & b & mask) != 0
#
#    # In "builder" style, a cheap approximation if you *do* have comparison
#    # at the node level is not allowed here, so assume you have a helper
#    # to compute "any bit set":
#    not_a = builder.buildNot(a)
#    t = builder.buildAnd(not_a, b)
#    t = builder.buildAnd(t, axorb)  # restrict to differing bits
#    # Result: if any bit in t is 1, then a < b
#    a_lt_b = builder.buildOrReduce(t)  # OR-reduce all bits to 1-bit
#
#    return a_lt_b


def _icmp_ugt(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    return _icmp_ult(builder, b, a)


def _icmp_ule(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    return builder.buildNot(_icmp_ugt(builder, a, b))


def _icmp_uge(builder: HlsNetlistBuilder, a: HlsNetNodeOut, b: HlsNetNodeOut):
    return builder.buildNot(_icmp_ult(builder, a, b))


_CMP_LOWERING_FNs = {
    # fn, isSigned, hasEq
    HwtOps.SLT: (_icmp_slt, True, False),
    HwtOps.SGT: (_icmp_sgt, True, False),
    HwtOps.SLE: (_icmp_sle, True, True),
    HwtOps.SGE: (_icmp_sge, True, True),

    HwtOps.ULT: (_icmp_ult, False, False),
    HwtOps.UGT: (_icmp_ugt, False, False),
    HwtOps.ULE: (_icmp_ule, False, True),
    HwtOps.UGE: (_icmp_uge, False, True),
}


def netlistReduceCmpToSubstractMsbCheck(n: HlsNetNodeOperator, worklist: SetList[HlsNetNode]):
    """
    Lowering cmp to substraction allows for merging of this node into adder trees which is likely
    to improve timing analysis precission in the cost of reduced readability of produced code.
    """
    # lt/gt can be realized using only substract
    op = n.operator
    loweringFn = _CMP_LOWERING_FNs.get(op)
    if loweringFn is None:
        return False
    loweringFn, isSigned, hasEq = loweringFn
    a, b = n.dependsOn
    builder = HlsNetlistBuilderWithWorklist(n.getHlsNetlistBuilder(), worklist)
    if hasEq:
        # HwtOps.SLE, HwtOps.SGE, HwtOps.ULE, HwtOps.UGE
        # le/ge needs extra "not" (and is also more complex HW wise), that is why we wnat it to convert it to variant with eq check
        bAsConst = getConstOfOutput(b)
        if bAsConst is not None and bAsConst._is_full_valid():
            w = a._dtype.bit_length()
            bAsConst = int(bAsConst)
            if isSigned:
                bAsConst = to_signed(bAsConst, w)
            # le/ge can be converted to lt/gt if RHS is constant by +/- 1
            if op == HwtOps.SLE:
                signedMax = mask(w - 1)
                if bAsConst == signedMax:
                    replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist)
                    return True
                bAsConst += 1
                op = HwtOps.SLT
            elif op == HwtOps.SGE:
                signedMin = to_signed(1 << (w - 1), w)
                if bAsConst == signedMin:
                    replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist)
                    return True
                bAsConst -= 1
                op = HwtOps.SGT
            elif op == HwtOps.ULE:
                unsignedMax = mask(w)
                if bAsConst == unsignedMax:
                    replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist)
                    return True
                bAsConst += 1
                op = HwtOps.ULT
            elif op == HwtOps.UGE:
                unsignedMin = 0
                if bAsConst == unsignedMin:
                    replaceOperatorNodeWith(n, builder.buildConstBit(1), worklist)
                    return True
                bAsConst -= 1
                op = HwtOps.UGT
            else:
                raise NotImplementedError(op)

            if isSigned:
                bAsConst = to_unsigned(bAsConst, w)
            b = builder.buildConst(a._dtype.from_py(bAsConst))
            loweringFn, isSigned, hasEq = _CMP_LOWERING_FNs.get(op)

    # unsigned variant needs +1b to check for borrow
    r = loweringFn(builder, a, b)
    replaceOperatorNodeWith(n, r, worklist)
    return True
