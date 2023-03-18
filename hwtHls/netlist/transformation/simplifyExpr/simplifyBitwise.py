from typing import Set, List, Generator, Tuple, Literal

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, \
    unlink_hls_nodes, link_hls_nodes
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith, \
    disconnectAllInputs
from pyMathBitPrecise.bit_utils import get_bit, mask, ValidityError
from hdlConvertorAst.to.hdlUtils import iter_with_last


def iter1and0sequences(v: BitsVal) -> Generator[Tuple[Literal[1, 0], int], None, None]:
    """
    :note: same as ConstBitPartsAnalysisContext::iter1and0sequences
    :note: lower first
    :return: generators of tuples in format 0/1, width
    """
    # if the bit in c is 0 the output bit should be also 0 else it is bit from v
    l_1: int = -1  # start of 1 sequence, -1 as invalid value
    l_0: int = -1  # start of 0 sequence, -1 as invalid value
    endIndex = v._dtype.bit_length() - 1
    if not v._is_full_valid():
        raise NotImplementedError(v)
    _v = v.val
    for h in range(endIndex + 1):
        curBit = get_bit(_v, h)
        if l_1 == -1 and curBit:
            l_1 = h  # start of 1 sequence
        elif l_0 == -1 and not curBit:
            l_0 = h  # start of 0 sequence

        last = h == endIndex
        if l_1 != -1 and (last or not get_bit(_v, h + 1)):
            # end of 1 sequence found
            w = h - l_1 + 1
            yield (1, w)
            l_1 = -1  # reset start
        elif l_0 != -1 and (last or get_bit(_v, h + 1)):
            # end of 0 sequence found
            w = h - l_0 + 1
            yield (0, w)
            l_0 = -1  # reset start


def isAll0OrAll1(v: BitsVal):
    vInt = int(v)
    return vInt == 0 or vInt == mask(v._dtype.bit_length())


def netlistReduceMux(n: HlsNetNodeMux, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    if len(n._inputs) == 1:
        # mux x = x
        i: HlsNetNodeOut = n.dependsOn[0]
        replaceOperatorNodeWith(n, i, worklist, removed)
        return True
    builder: HlsNetlistBuilder = n.netlist.builder
    # resolve constant conditions
    newOps: List[HlsNetNodeIn] = []
    newValSet: Set[HlsNetNodeIn] = set()
    for (v, c) in n._iterValueConditionDriverPairs():
        if c is not None and isinstance(c.obj, HlsNetNodeConst):
            if c.obj.val:
                newOps.append(v)
                newValSet.add(v)
                break
        else:
            newOps.append(v)
            newValSet.add(v)
            if c is not None:
                newOps.append(c)

    singleVal = len(newValSet) == 1
    newOpsLen = len(newOps)
    if newOpsLen != len(n._inputs) or singleVal:
        if newOpsLen == 1 or (singleVal and newOpsLen % 2 == 1):
            i: HlsNetNodeOut = newOps[0]
        else:
            i = builder.buildMux(n._outputs[0]._dtype, tuple(newOps))

        replaceOperatorNodeWith(n, i, worklist, removed)
        return True

    # merge mux to only user which is mux if this is the case and it is possible
    if len(n._inputs) % 2 == 1:
        assert len(n._outputs) == 1, n
        if len(n.usedBy[0]) == 1:
            u: HlsNetNodeIn = n.usedBy[0][0]
            if isinstance(u.obj, HlsNetNodeMux) and len(u.obj._inputs) % 2 == 1:
                # if u.in_i == 0:
                #    raise NotImplementedError()
                # el
                if u.in_i == len(u.obj._inputs) - 1:
                    newOps = u.obj.dependsOn[:-1] + n.dependsOn
                    res = builder.buildMux(n._outputs[0]._dtype, tuple(newOps))
                    replaceOperatorNodeWith(u.obj, res, worklist, removed)
                    disconnectAllInputs(n, worklist)
                    removed.add(n)
                    return True

    # x ? x: v1 -> x | v1
    if len(n._inputs) == 3:
        v0, c, v1 = n.dependsOn
        if v0 is c:
            newO = builder.buildOr(c, v1)
            replaceOperatorNodeWith(n, newO, worklist, removed)
            return True

    if len(n._inputs) >= 3:
        # try to format mux to a format where each condition is comparison with EQ operator
        # so the mux behaves like switch-case statement id it is suitable for ROM extraction
        cases = tuple(n._iterValueConditionDriverPairs())
        if cases[-1][1] is None:
            # if contains else it may be possible to swap last two cases if required
            everyNonLastConditionIsEq = True
            everyConditionIsEq = True
            lastConditionIsNe = False
            preLastcaseIndex = len(cases) - 2
            for i, (v, c) in enumerate(cases):
                if c is None:
                    break
                if isinstance(c.obj, HlsNetNodeOperator):
                    op = c.obj.operator
                    if i == preLastcaseIndex:
                        lastConditionIsNe = op == AllOps.NE
                        everyConditionIsEq = everyNonLastConditionIsEq and  op == AllOps.EQ
                    else:
                        everyNonLastConditionIsEq = op == AllOps.EQ
                else:
                    everyNonLastConditionIsEq = False
                    break

            if everyNonLastConditionIsEq and lastConditionIsNe:
                # flip last condition NE -> EQ and swap cases
                origNe = cases[-2][1]
                origNeArgs = origNe.obj.dependsOn
                cIn = n._inputs[preLastcaseIndex * 2 + 1]
                unlink_hls_nodes(origNe, cIn)
                worklist.append(origNe.obj)
                newEq = builder.buildEq(origNeArgs[0], origNeArgs[1])
                link_hls_nodes(newEq, cIn)
                return True

            elif everyConditionIsEq:
                # try extract ROM
                romCompatible = True
                romData = {}
                index = None
                for (v, c) in cases:
                    if c is not None:
                        cOp0, cOp1 = c.obj.dependsOn
                        if index is None:
                            index = cOp0

                        if cOp0 is not index:
                            romCompatible = False
                            break

                        if isinstance(cOp1.obj, HlsNetNodeConst):
                            try:
                                cOp1 = int(cOp1.obj.val)
                            except ValidityError:
                                raise AssertionError(n, "value specified for undefined index in ROM")
                            if isinstance(v.obj, HlsNetNodeConst):
                                romData[cOp1] = v.obj.val
                            else:
                                romCompatible = False
                                break
                        else:
                            romCompatible = False
                            break
                    else:
                        itemCnt = 2 ** index._dtype.bit_length()
                        if len(romData) == itemCnt - 1 and itemCnt - 1 not in romData.keys():
                            # if the else branch of the mux contains trully the last item of the ROM
                            if isinstance(v.obj, HlsNetNodeConst):
                                romData[itemCnt - 1] = v.obj.val
                            else:
                                romCompatible = False
                                break
                        else:
                            romCompatible = False
                            break

                assert index is not None
                if romCompatible:
                    rom = builder.buildRom(romData, index)
                    replaceOperatorNodeWith(n, rom, worklist, removed)
                    return True

    return False


def netlistReduceNot(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    builder: HlsNetlistBuilder = n.netlist.builder
    o0, = n.dependsOn
    o0Const = isinstance(o0.obj, HlsNetNodeConst)
    newO = None
    if o0Const:
        newO = builder.buildConst(~o0.obj.val)
    elif isinstance(o0, HlsNetNodeOut) and isinstance(o0.obj, HlsNetNodeOperator) and o0.obj.operator == AllOps.NOT:
        # ~~x = x
        newO = o0.obj.dependsOn[0]

    if newO is not None:
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    return False


def netlistReduceAndOrXor(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    builder: HlsNetlistBuilder = n.netlist.builder
    # search for const in for commutative operator
    o0, o1 = n.dependsOn
    o0Const = isinstance(o0.obj, HlsNetNodeConst)
    o1Const = isinstance(o1.obj, HlsNetNodeConst)
    newO = None
    t = o0._dtype

    if o0Const and not o1Const:
        # make sure const is o1 if const is in operands
        o0, o1 = o1, o0
        o0Const = False
        o1Const = True

    if n.operator == AllOps.AND:
        if o0Const and o1Const:
            newO = builder.buildConst(o0.obj.val & o1.obj.val)

        elif o1Const:
            # to concatenation of o0 bits and 0s after const mask is applied
            if isAll0OrAll1(o1.obj.val):
                if int(o1.obj.val):
                    # x & 1 = x
                    newO = o0
                else:
                    # x & 0 = 0
                    newO = builder.buildConstPy(t, 0)

            else:
                concatMembers = []
                offset = 0
                for bitVal, width in iter1and0sequences(o1.obj.val):
                    if bitVal:
                        # x & 1 = x
                        v0 = builder.buildIndexConstSlice(Bits(width), o0, offset + width, offset)
                    else:
                        # x & 0 = 0
                        v0 = builder.buildConstPy(Bits(width), 0)

                    concatMembers.append(v0)

                    offset += width
                newO = builder.buildConcatVariadic(tuple(concatMembers))

        elif o0 == o1:
            # x & x = x
            newO = o0

    elif n.operator == AllOps.OR:
        if o0Const and o1Const:
            newO = builder.buildConst(o0.obj.val | o1.obj.val)

        elif o1Const:
            if isAll0OrAll1(o1.obj.val):
                if int(o1.obj.val):
                    # x | 1 = 1
                    newO = builder.buildConst(t.from_py(mask(t.bit_length())))
                else:
                    # x | 0 = x
                    newO = o0

            else:
                concatMembers = []
                offset = 0
                for bitVal, width in iter1and0sequences(o1.obj.val):
                    if bitVal:
                        # x | 1 = 1
                        v0 = builder.buildConst(Bits(width).from_py(mask(width)))
                    else:
                        # x | 0 = x
                        v0 = builder.buildIndexConstSlice(Bits(width), o0, offset + width, offset)

                    concatMembers.append(v0)

                    offset += width
                newO = builder.buildConcatVariadic(tuple(concatMembers))

        elif o0 == o1:
            # x | x = x
            newO = o0

    elif n.operator == AllOps.XOR:
        if o0Const and o1Const:
            newO = builder.buildConst(o0.obj.val ^ o1.obj.val)

        elif o1Const:
            # perform reduction by constant
            if isAll0OrAll1(o1.obj.val):
                if int(o1.obj.val):
                    # x ^ 1 = ~x
                    newO = builder.buildNot(o0)
                else:
                    # x ^ 0 = x
                    newO = o0
            else:
                concatMembers = []
                offset = 0
                for bitVal, width in iter1and0sequences(o1.obj.val):
                    v0 = builder.buildIndexConstSlice(Bits(width), o0, offset + width, offset)
                    if bitVal:
                        v0 = builder.buildNot(v0)
                    concatMembers.append(v0)
                    offset += width

                newO = builder.buildConcatVariadic(tuple(concatMembers))

        elif o0 == o1:
            # x ^ x = 0
            newO = builder.buildConst(t.from_py(0))

    if newO is not None:
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    return False
