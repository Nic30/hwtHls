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
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith, \
    disconnectAllInputs
from pyMathBitPrecise.bit_utils import get_bit, mask


def iter1and0sequences(v: BitsVal) -> Generator[Tuple[Literal[1, 0], int], None, None]:
    """
    :note: same as ConstBitPartsAnalysisContext::iter1and0sequences
    :note: lower first
    :returns: generators of tuples in format 0/1, width
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
            i = n.netlist.builder.buildMux(n._outputs[0]._dtype, tuple(newOps))

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
                    res = n.netlist.builder.buildMux(n._outputs[0]._dtype, tuple(newOps))
                    replaceOperatorNodeWith(u.obj, res, worklist, removed)
                    disconnectAllInputs(n, worklist)
                    removed.add(n)
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
                    newO = builder.buildConstPy(o0._dtype, 9)

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
                    newO = builder.buildConst(o0._dtype.from_py(mask(o0._dtype.bit_length())))
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
            newO = builder.buildConst(o0._dtype.from_py(0))
        
    if newO is not None:
        replaceOperatorNodeWith(n, newO, worklist, removed)
        return True

    return False