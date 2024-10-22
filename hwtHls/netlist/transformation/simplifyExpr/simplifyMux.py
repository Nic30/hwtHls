from typing import Set, List, Generator, Tuple, Optional, Dict, Union, Literal

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef, ALWAYS_COMMUTATIVE_OPS
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.slice import HSlice
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import replaceOperatorNodeWith, \
    disconnectAllInputs
from pyMathBitPrecise.bit_utils import ValidityError


def netlistReduceMuxWitAllSameValues(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    commonVal: Union[Literal[NOT_SPECIFIED], HConst, HlsNetNodeOut] = NOT_SPECIFIED
    commonValIsConst = False
    for val, _ in n._iterValueConditionDriverPairs():
        if commonVal is val:
            continue
        valAsConst = getConstOfOutput(val)
        if valAsConst is not None:
            if commonVal is NOT_SPECIFIED:
                commonVal = valAsConst
                commonValIsConst = True
            elif not commonValIsConst or not (commonVal == valAsConst):
                # :note: HConst !=  operator is overloaded and would raise ValidityError if constants hold invalid ('x') value
                return False
        else:
            if commonVal is NOT_SPECIFIED:
                commonVal = val
            else:
                # commonVal != val
                return False

    # all values were same
    newO = n.dependsOn[0]
    replaceOperatorNodeWith(n, newO, worklist)
    return True


def netlistReduceMuxToRom(builder: HlsNetlistBuilder, n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    # try to format mux to a format where each condition is comparison with EQ operator
    # so the mux behaves like switch-case statement id it is suitable for ROM extraction
    cases = tuple(n._iterValueConditionDriverPairs())
    if cases[-1][1] is not None:
        return False

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
                lastConditionIsNe = op == HwtOps.NE
                everyConditionIsEq = everyNonLastConditionIsEq and op == HwtOps.EQ
            else:
                everyNonLastConditionIsEq &= op == HwtOps.EQ
        else:
            everyConditionIsEq = False
            everyNonLastConditionIsEq = False
            break

    if everyNonLastConditionIsEq and lastConditionIsNe:
        # flip last condition NE -> EQ and swap cases
        origNe = cases[-2][1]
        origNeArgs = origNe.obj.dependsOn
        cIn = n._inputs[preLastcaseIndex * 2 + 1]
        cIn.disconnectFromHlsOut(origNe)
        worklist.append(origNe.obj)
        newEq = builder.buildEq(origNeArgs[0], origNeArgs[1])
        newEq.connectHlsIn(cIn)

        v0In = n._inputs[preLastcaseIndex * 2]
        v0 = n.dependsOn[preLastcaseIndex * 2]
        v1In = n._inputs[preLastcaseIndex * 2 + 2]
        v1 = n.dependsOn[preLastcaseIndex * 2 + 2]
        v0In.disconnectFromHlsOut(v0)
        v1In.disconnectFromHlsOut(v1)
        v0.connectHlsIn(v1In)
        v1.connectHlsIn(v0In)
        everyConditionIsEq = True
        lastConditionIsNe = False
        cases = tuple(n._iterValueConditionDriverPairs())

    if everyConditionIsEq:
        # try extract ROM
        romCompatible = True
        romData = {}
        index = None
        for (v, c) in cases:
            if c is not None:
                if not isinstance(c.obj, HlsNetNodeOperator) or len(c.obj.dependsOn) != 2:
                    romCompatible = False
                    break

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
                if index is None:
                    romCompatible = False
                    break

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

        if romCompatible:
            assert index is not None
            rom = builder.buildRom(romData, index)
            replaceOperatorNodeWith(n, rom, worklist)
            return True

    return False


def popConcatOfSlices(o: HlsNetNodeOut, depthLimit: int) -> Generator[Tuple[HlsNetNodeOut, int, int], None, None]:
    obj = o.obj

    if not isinstance(obj, HlsNetNodeOperator):
        yield (o, 0, o._dtype.bit_length())
        return

    if depthLimit > 0 and obj.operator == HwtOps.CONCAT:
        for op in obj.dependsOn:
            yield from popConcatOfSlices(op, depthLimit - 1)
        return
    elif obj.operator == HwtOps.INDEX and isinstance(o._dtype, HBits) and isinstance(obj.dependsOn[1].obj, HlsNetNodeConst):
        v, indx = obj.dependsOn
        indx = indx.obj.val
        if isinstance(indx._dtype, HBits):
            indx = int(indx)
            yield (v, indx, indx + 1)
        else:
            assert isinstance(indx._dtype, HSlice), indx
            slice_:slice = indx.val
            start = int(slice_.start)
            stop = int(slice_.stop)
            step = int(slice_.step)
            assert step == -1, (step, indx)
            assert stop < start, (indx, stop, start)
            yield (v, stop, start)  # stop=LSB index, start=MSB index
        return
    else:
        yield (o, 0, o._dtype.bit_length())


def netlistReduceMuxToShift(builder: HlsNetlistBuilder, n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    assert len(n._inputs) % 2 == 1, n
    msbShiftIn = None
    shiftedVal = None
    lsbShiftIn = None
    # Tuple(condition, shiftAmountValue, shiftedValueConcatMembers)
    shiftVariants: List[Tuple[HlsNetNodeOut, Optional[int], Tuple[HlsNetNodeOut, int, int]]] = []
    for _v, c in n._iterValueConditionDriverPairs():
        v = tuple(popConcatOfSlices(_v, 1))
        if len(v) == 1:
            if shiftedVal is not None:
                return False
            shiftedVal = [c, None, v]
        else:
            shiftVariants.append([c, None, v])

    if (shiftedVal is not None and shiftVariants) or len(shiftVariants) > 0:
        if shiftedVal is None:
            return False  # [todo] support shifts which do not have 0-bit shift value where variant value is shiftedVal
        else:
            # shiftedVal can actually be msbShiftIn or lsbShiftIn
            shiftInCandidates = []
            for variant in shiftVariants:
                # check if every value operand is:
                # * v or
                # * msbShiftIn
                # * lsbShiftIn
                # * v shift or
                # *  Concat(msbShiftIn slice, v slice)
                # *  Concat(v slice, lsbShitIn slice)
                v = variant[2]
                if len(v) == 1:
                    # this is not concat, it must be msbShiftIn lsbShiftIn
                    if len(shiftInCandidates) == 2:
                        return False  # there can be at most msbShiftIn and lsbShiftIn

                    shiftInCandidates.append(variant)
                else:
                    # find position of shiftedVal in variant
                    shiftedValPort, shiftedValBeginBitI, shiftedValEndBitI = shiftedVal
                    offset = 0
                    found = False
                    for vMember, beginBitI, endBitI in v:
                        if vMember is shiftedValPort:
                            # [todo] msbShiftIn/lsbShiftIn can be shiftedVal or part of it
                            # arithmetic shift right
                            raise NotImplementedError()
                            found = True
                        else:
                            assert beginBitI < endBitI
                            offset += endBitI - beginBitI

                    if not found:
                        # this does not contain shiftedValPort
                        if len(shiftInCandidates) == 2:
                            return False  # there can be at most msbShiftIn and lsbShiftIn
                        shiftInCandidates.append(variant)

            if len(shiftInCandidates) == len(shiftVariants):
                # all variants did not contain shiftedValPort and thus this is not a shift
                return False
            else:
                raise NotImplementedError()

        raise NotImplementedError()

    # check if all condition operands can are form of equality comparison
    return False

# def netlistReduceMuxOverspecifiedConditions(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
#    """
#    convert
#
#    MUX v0 c0 v1 ~c0 & c1 v2
#    to
#    MUX v0 c0 v1 c1 v2
#    """


def netlistReduceMuxConstantConditionsAndChildMuxSink(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    # resolve constant conditions
    newCondSet: Set[HlsNetNodeOut] = set()
    newOps: List[HlsNetNodeIn] = []
    newValSet: Set[HlsNetNodeIn] = set()
    for (v, c) in n._iterValueConditionDriverPairs():
        if c is not None and isinstance(c.obj, HlsNetNodeConst):
            if c.obj.val:
                newOps.append(v)
                newValSet.add(v)
                break
        else:
            childMux = v.obj
            if isinstance(childMux, HlsNetNodeMux) and all(u.obj == n and u.in_i % 2 == 0
                                                        for u in childMux.usedBy[v.out_i]):
                # if it is used only by value operands of n
                # inline child mux
                for (v1, c1) in childMux._iterValueConditionDriverPairs():
                    if c is not None:
                        if c1 is None:
                            c1 = c
                        else:
                            c1 = builder.buildAnd(c, c1)

                    if c1 not in newCondSet:
                        newOps.append(v1)
                        newValSet.add(v1)

                        if c1 is not None:
                            newOps.append(c1)
                            newCondSet.add(c1)

            elif c not in newCondSet:
                newOps.append(v)
                newValSet.add(v)
                if c is not None:
                    newOps.append(c)
                    newCondSet.add(c)

    singleVal = len(newValSet) == 1
    newOpsLen = len(newOps)
    if newOpsLen != len(n._inputs) or singleVal:
        # some conditions were constant or mux switches just 1 value
        if newOpsLen == 1 or (singleVal and newOpsLen % 2 == 1):
            # every possible case has the same value
            i: HlsNetNodeOut = newOps[0]
        else:
            i = builder.buildMux(n._outputs[0]._dtype, tuple(newOps))
            i.obj.tryToInheritName(n)
            worklist.append(i.obj)  # may have become ROM

        replaceOperatorNodeWith(n, i, worklist)
        return True

    return False


def netlistReduceMuxToOr(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    """
    .. code-block::
        x ? x: v1 -> x | v1
    """
    assert len(n.dependsOn) == 3, (n, "It should be checked in advance that this is 3 operand mux")
    v0, c, v1 = n.dependsOn
    builder = n.getHlsNetlistBuilder()
    if v0 is c:
        newO = builder.buildOr(c, v1)
        replaceOperatorNodeWith(n, newO, worklist)
        return True

    # if one operand is undef, replace this with other value operand
    v0Const = getConstOfOutput(v0)
    if v0Const is not None and v0Const.vld_mask == 0:
        replaceOperatorNodeWith(n, v1, worklist)
        return True
    v1Const = getConstOfOutput(v1)
    if v1Const is not None and v1Const.vld_mask == 0:
        replaceOperatorNodeWith(n, v0, worklist)
        return True

    if v0Const is not None and\
        v1Const is not None and \
        v0._dtype.bit_length() == 1 and\
        v0Const._is_full_valid() and v1Const._is_full_valid():
        # c ? 1 : 0 -> c
        if v0Const and not v1Const:
            replaceOperatorNodeWith(n, c, worklist)
            return True
        # c ? 0 : 1 -> ~c
        if not v0Const and v1Const:
            replaceOperatorNodeWith(n, builder.buildNot(c), worklist)
            return True

    return False


def netlistReduceMuxToAndOrNot(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    """
    .. code-block::
        v0 == v1, v0 if c else v1 = v0
        v0 if 'X' else v1 = 'X'
        v0 if 1 else v1 = v0
        v0 if 0 else v1 = v1
        1 if c else 0 = c
        0 if c else 1 = ~c
        1 if c else v1 = c | v1
        0 if c else v1 = ~c & v1
        v0 if c else 1 = v0 | ~c
        v0 if c else 0 = v0 & c
                       
    """
    assert len(n.dependsOn) == 3, (n, "It should be checked in advance that this is 3 operand mux")
    newO = n._outputs[0]
    resT = newO._dtype
    while True:
        # this loop purpose is only to jump on end using break,
        # it performs 1 iteration at most
        v0, c, v1 = n.dependsOn
        if v0 is v1:
            # v0 == v1, v0 if c else v1 = v0
            newO = v0
            break

        builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
        cc = getConstOfOutput(c)
        if cc is not None:
            if not cc._is_full_valid():
                # v0 if 'X' else v1 = 'X'
                if resT.bit_length() == 1:
                    newO = c
                else:
                    newO = builder.buildConst(resT.from_py(None))
                break
            elif int(cc):
                # v0 if 1 else v1 = v0
                newO = v0
                break
            else:
                # v0 if 0 else v1 = v1
                newO = v1
                break

        v0c = getConstOfOutput(v0)
        v1c = getConstOfOutput(v1)
        if v0c is not None and v1c is not None and v0c == v1c:
            # v0 == v1, v0 if c else v1 = v0
            newO = v0
            break

        if resT.bit_length() == 1:
            if v0c is not None and v0c._is_full_valid():
                v0c = int(v0c)
                if v1c is not None and v1c._is_full_valid():
                    v1c = int(v1c)

                    if v0c and not v1c:
                        # 1 if c else 0 = c
                        newO = c
                        break
                    elif not v0c and v1c:
                        # 0 if c else 1 = ~c
                        newO = builder.buildNot(c)
                        break
                else:
                    if v0c:
                        # 1 if c else v1 = c | v1
                        newO = builder.buildOr(c, v1)
                        break
                    else:
                        # 0 if c else v1 = ~c & v1
                        newO = builder.buildAnd(builder.buildNot(c), v1)
                        break

            elif v1c is not None and v1c._is_full_valid():
                v1c = int(v1c)
                if v1c:
                    # v0 if c else 1 = v0 | ~c
                    newO = builder.buildOr(builder.buildNot(c), v0)
                    break
                else:
                    # v0 if c else 0 = v0 & c
                    newO = builder.buildAnd(c, v0)
                    break
        break

    if newO is not n._outputs[0]:
        replaceOperatorNodeWith(n, newO, worklist)
        return True

    return False


def netlistReduceMuxMergeToUserMux(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    """
    merge mux to only user which is mux if this is the case and it is possible
    """
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
                    builder = n.getHlsNetlistBuilder()
                    res = builder.buildMux(n._outputs[0]._dtype, tuple(newOps))
                    replaceOperatorNodeWith(u.obj, res, worklist)
                    disconnectAllInputs(n, worklist)
                    n.markAsRemoved()
                    return True

    return False


def netlistReduceMuxUnnegateConditions(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    """
    supports arbitrary number of operands, swaps last two values if last condition is negated to remove negation of c
    
    .. code-block::
        ~c ? v0: v1 -> c ? v1: v0
    """
    inpCnt = len(n._inputs)
    if inpCnt % 2 == 1 and inpCnt >= 3:
        v0, c, v1 = n.dependsOn[-3:]
        if isinstance(c.obj, HlsNetNodeOperator) and c.obj.operator == HwtOps.NOT:
            cIn = n._inputs[-2]
            cIn.disconnectFromHlsOut(c)
            worklist.append(c.obj)
            c.obj.dependsOn[0].connectHlsIn(cIn)
            v0In = n._inputs[-3]
            v1In = n._inputs[-1]
            v0In.disconnectFromHlsOut(v0)
            v1In.disconnectFromHlsOut(v1)
            v0.connectHlsIn(v1In)
            v1.connectHlsIn(v0In)
            return True
    return False


def _hasOperandOnIndex(n: HlsNetNode, index: Optional[int], operand: HlsNetNodeOut):
    return (index is None and operand in n.dependsOn) or\
           (index is not None and operand == n.dependsOn[index])


def _netlistReduceMuxSinkIncommingValueArithOperators_buildNewMux(n: HlsNetNodeMux,
                                                     worklist: SetList[HlsNetNode],
                                                     commonOperand: HlsNetNodeOut,
                                                     commonOperator:HOperatorDef,
                                                     commonOperandIndex:Optional[int],
                                                     constantValues: SetList[HlsNetNodeOut],
                                                     NEUTRAL_VALUE: Dict[HOperatorDef, int],
                                                     ):

    # sink extracted operators behind this MUX
    # if there are any
    builder = n.getHlsNetlistBuilder()
    neutralValueIsUsed = any(v is commonOperand for v, _ in n._iterValueConditionDriverPairs())
    resT = n._outputs[0]._dtype
    if neutralValueIsUsed:
        neutralValue = builder.buildConstPy(resT, NEUTRAL_VALUE[commonOperator])
    else:
        neutralValue = None

    newMuxArgs = []
    valueToAndConditionWith = None
    for v, c in n._iterValueConditionDriverPairs():
        _c = c
        # update condition for this item if required
        if valueToAndConditionWith is not None and c is not None:
            c = builder.buildAnd(valueToAndConditionWith, c)
            worklist.append(c.obj)

        if v is commonOperand:
            v = neutralValue
        elif v in constantValues:
            # skip constant operand and add it only in second mux
            if c is not None:
                valueToAndConditionWith = builder.buildAndOptional(valueToAndConditionWith, builder.buildNot(_c))
                worklist.append(valueToAndConditionWith.obj)

            continue
        else:
            o0, o1 = v.obj.dependsOn
            if o0 is commonOperand:
                v = o1
            else:
                assert o1 is commonOperand, (n, v, commonOperand)
                v = o0

        # :note: neutralValue is cleared if this condition will be just added
        #  and term is not required for later conditions
        valueToAndConditionWith = None

        newMuxArgs.append(v)
        worklist.append(v.obj)
        if c is not None:
            newMuxArgs.append(c)
            worklist.append(c.obj)

    newMux = builder.buildMux(resT, tuple(newMuxArgs), name=n.name)
    worklist.append(newMux.obj)
    if commonOperandIndex is None or commonOperandIndex == 0:
        newResOps = (commonOperand, newMux)
    else:
        assert commonOperandIndex == 1, (n, commonOperandIndex)
        newResOps = (newMux, commonOperand)

    newOp = builder.buildOp(commonOperator, None, resT, *newResOps, name=n.name, worklist=worklist)

    if constantValues:
        worklist.append(newOp.obj)
        newConstMuxOps = []
        valueToAndConditionWith = None
        seenConstantOpCnt = 0
        for v, c in n._iterValueConditionDriverPairs():
            _c = c
            if valueToAndConditionWith is not None and c is not None:
                # update condition for this item if required
                c = builder.buildAnd(valueToAndConditionWith, c)
                worklist.append(c.obj)

            if v in constantValues:
                valueToAndConditionWith = None
                # :note: neutralValue is cleared if this condition will be just added
                #  and term is not required for later conditions

                newConstMuxOps.append(v)
                worklist.append(v.obj)
                seenConstantOpCnt += 1
                if c is not None:
                    newConstMuxOps.append(c)
                    worklist.append(c.obj)
                    if seenConstantOpCnt == len(constantValues):
                        # there will be no other constant operand for this mux
                        # add default value
                        newConstMuxOps.append(newOp)
                        break

            else:
                if c is not None:
                    valueToAndConditionWith = builder.buildAndOptional(valueToAndConditionWith, builder.buildNot(_c))
                    worklist.append(valueToAndConditionWith.obj)

        newRes = builder.buildMux(resT, tuple(newConstMuxOps), name=n.name)
    else:
        newRes = newOp

    worklist.append(newRes.obj)
    replaceOperatorNodeWith(n, newRes, worklist)


def netlistReduceMuxSinkIncommingValueArithOperators(n: HlsNetNodeMux,
                                                     worklist: SetList[HlsNetNode],
                                                     SUPPORTED_OPS={HwtOps.ADD, HwtOps.SUB, HwtOps.MUL},
                                                     NEUTRAL_VALUE={HwtOps.ADD:0, HwtOps.SUB:0, HwtOps.MUL:1},
                                                     COMMUTATIVE_OPS=ALWAYS_COMMUTATIVE_OPS):
    """
    Sink arithmetic operators from value operands of this MUX
    
    .. code-block::python
        if c0:
            res = v + v0
        elif c1:
            res = v + v1
        elif c2:
            res = 99
        elif c3:
            res = v + v3
        else:
            res = v
    
        # to
        if c0:
            resTmp0 = v0
        elif c1:
            resTmp0 = v1
        elif ~c2 & c3:
            resTmp0 = v3
        else:
            resTmp0 = 0
        
        resTmp1 = v + resTmp0
        # :note: this final mux will be omitted if there is no constant value in original mux
        if ~c0 & ~c1 & c2:
            res = 99
        else:
            res = resTmp1
        
    :note: "v" from example may also be extractable and on any position
    """
    assert len(n.dependsOn) >= 3, (n, "minimum of 3 operands should be checked before this function is called")
    assert SUPPORTED_OPS
    candidate: Optional[HlsNetNodeOut] = None
    candidateCommonOperand: Optional[HlsNetNodeOut] = None
    candidateCommonOperandIndex: Optional[int] = None
    candidateOperator: Optional[HOperatorDef] = None

    toBeExtracted: SetList[HlsNetNodeOut] = SetList()
    constantValues: SetList[HlsNetNodeOut] = SetList()
    for v, _ in n._iterValueConditionDriverPairs():
        if v in toBeExtracted or v is candidateCommonOperand:
            continue
        if getConstOfOutput(v) is not None:
            constantValues.append(v)
            continue

        elif isinstance(v.obj, HlsNetNodeOperator):
            vNode = v.obj
            if candidateOperator is None:
                if vNode.operator in SUPPORTED_OPS:
                    # first extractable value seen
                    candidate = v
                    candidateOperator = vNode.operator
                    candidateCommonOperand = vNode.dependsOn[0]
                    if candidateOperator not in COMMUTATIVE_OPS:
                        candidateCommonOperandIndex = 0
                    else:
                        candidateCommonOperandIndex = None
                    continue

            elif vNode.operator == candidateOperator:
                if _hasOperandOnIndex(vNode, candidateCommonOperandIndex, candidateCommonOperand):
                    toBeExtracted.append(v)
                    continue
                elif not toBeExtracted:
                    # this is first same operator found, it is possible to swap searched operand if if operator is commutative
                    assert candidateCommonOperandIndex != 1
                    if candidate.obj.dependsOn[1] == vNode.dependsOn[1]:
                        candidateCommonOperand = vNode.dependsOn[1]
                        if candidateCommonOperandIndex is not None:
                            candidateCommonOperandIndex = 1
                        toBeExtracted.append(v)
                        continue

            elif vNode.operator in SUPPORTED_OPS and not toBeExtracted:
                # Found another extractable operator, but it is incompatible with current candidate
                # Try swap candidate with current value
                candidateUpdated = False
                for nOpIndex in range(2):
                    if vNode.dependsOn[nOpIndex] is candidate:
                        _candidate = candidate
                        candidate = v
                        candidateOperator = vNode.operator
                        candidateCommonOperand = _candidate
                        candidateCommonOperandIndex = nOpIndex if vNode.operator in COMMUTATIVE_OPS else None
                        candidateUpdated = True
                        break
                if candidateUpdated:
                    continue

        if candidateCommonOperand is None:
            candidateCommonOperand = v
        elif candidateCommonOperand is not v:
            # it was just found that at least 2 input values are not extractable
            return

    if toBeExtracted:
        _netlistReduceMuxSinkIncommingValueArithOperators_buildNewMux(
            n, worklist,
            candidateCommonOperand, candidateOperator, candidateCommonOperandIndex, constantValues, NEUTRAL_VALUE)
        return True
    else:
        return False


def netlistReduceMux(n: HlsNetNodeMux, worklist: SetList[HlsNetNode]):
    inpCnt = len(n._inputs)
    if inpCnt == 1:
        # mux x = x
        i: HlsNetNodeOut = n.dependsOn[0]
        replaceOperatorNodeWith(n, i, worklist)
        return True

    if netlistReduceMuxConstantConditionsAndChildMuxSink(n, worklist):
        return True

    if netlistReduceMuxMergeToUserMux(n, worklist):
        return True
    if inpCnt == 3:
        if netlistReduceMuxToOr(n, worklist):
            return True
        elif netlistReduceMuxToAndOrNot(n, worklist):
            return True

    builder: HlsNetlistBuilder = n.getHlsNetlistBuilder()
    # search large ROMs implemented as MUX
    if inpCnt >= 3:
        if netlistReduceMuxWitAllSameValues(n, worklist):
            return True

        elif netlistReduceMuxToRom(builder, n, worklist):
            return True

    if inpCnt % 2 == 1:
        if inpCnt >= 3:
            if netlistReduceMuxUnnegateConditions(n, worklist):
                return True

        if inpCnt > 2:
            if netlistReduceMuxToShift(builder, n, worklist):
                return True
            if netlistReduceMuxSinkIncommingValueArithOperators(n, worklist):
                return True

    return False
