from typing import Set, List, Generator, Tuple, Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.slice import HSlice
from hwt.pyUtils.setList import SetList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, \
    unlink_hls_nodes, link_hls_nodes
from hwtHls.netlist.transformation.simplifyUtils import replaceOperatorNodeWith, \
    disconnectAllInputs, getConstOfOutput
from pyMathBitPrecise.bit_utils import ValidityError


def netlistReduceMuxToRom(builder: HlsNetlistBuilder, n: HlsNetNodeMux, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
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
        unlink_hls_nodes(origNe, cIn)
        worklist.append(origNe.obj)
        newEq = builder.buildEq(origNeArgs[0], origNeArgs[1])
        link_hls_nodes(newEq, cIn)

        v0In = n._inputs[preLastcaseIndex * 2]
        v0 = n.dependsOn[preLastcaseIndex * 2]
        v1In = n._inputs[preLastcaseIndex * 2 + 2]
        v1 = n.dependsOn[preLastcaseIndex * 2 + 2]
        unlink_hls_nodes(v0, v0In)
        unlink_hls_nodes(v1, v1In)
        link_hls_nodes(v0, v1In)
        link_hls_nodes(v1, v0In)
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
            replaceOperatorNodeWith(n, rom, worklist, removed)
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
    elif obj.operator == HwtOps.INDEX and isinstance(o._dtype, HBits):
        v, indx = obj.dependsOn
        assert isinstance(indx.obj, HlsNetNodeConst), indx
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


def netlistReduceMuxToShift(builder: HlsNetlistBuilder, n: HlsNetNodeMux, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
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

# def netlistReduceMuxOverspecifiedConditions(n: HlsNetNodeMux, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
#    """
#    convert
#
#    MUX v0 c0 v1 ~c0 & c1 v2
#    to
#    MUX v0 c0 v1 c1 v2
#    """


def netlistReduceMuxConstantConditionsAndChildMuxSink(n: HlsNetNodeMux, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
    builder: HlsNetlistBuilder = n.netlist.builder
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
            if i.obj.name is None:
                i.obj.name = n.name
            worklist.append(i.obj)  # may have become ROM

        replaceOperatorNodeWith(n, i, worklist, removed)
        return True

    return False


def netlistReduceMux(n: HlsNetNodeMux, worklist: SetList[HlsNetNode], removed: Set[HlsNetNode]):
    inpCnt = len(n._inputs)
    if inpCnt == 1:
        # mux x = x
        i: HlsNetNodeOut = n.dependsOn[0]
        replaceOperatorNodeWith(n, i, worklist, removed)
        return True

    if netlistReduceMuxConstantConditionsAndChildMuxSink(n, worklist, removed):
        return True

    builder: HlsNetlistBuilder = n.netlist.builder

    # merge mux to only user which is mux if this is the case and it is possible
    if inpCnt % 2 == 1:
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
    if inpCnt == 3:
        v0, c, v1 = n.dependsOn
        if v0 is c:
            newO = builder.buildOr(c, v1)
            replaceOperatorNodeWith(n, newO, worklist, removed)
            return True
        # if one operand is undef, replace this with other value operand
        v0Const = getConstOfOutput(v0)
        if v0Const is not None and v0Const.vld_mask == 0:
            replaceOperatorNodeWith(n, v1, worklist, removed)
            return True
        v1Const = getConstOfOutput(v1)
        if v1Const is not None and v1Const.vld_mask == 0:
            replaceOperatorNodeWith(n, v0, worklist, removed)
            return True

    # search large ROMs implemented as MUX
    if inpCnt >= 3:
        if netlistReduceMuxToRom(builder, n, worklist, removed):
            return True

    # ~c ? v0: v1 -> c ? v1: v0 (supports arbitrary number of operands, swaps last two values if last condition is negated to remove negation of c)
    if inpCnt % 2 == 1 and inpCnt >= 3:
        v0, c, v1 = n.dependsOn[-3:]
        if isinstance(c.obj, HlsNetNodeOperator) and c.obj.operator == HwtOps.NOT:
            cIn = n._inputs[-2]
            unlink_hls_nodes(c, cIn)
            worklist.append(c.obj)
            link_hls_nodes(c.obj.dependsOn[0], cIn)
            v0In = n._inputs[-3]
            v1In = n._inputs[-1]
            unlink_hls_nodes(v0, v0In)
            unlink_hls_nodes(v1, v1In)
            link_hls_nodes(v0, v1In)
            link_hls_nodes(v1, v0In)
            return True

    if inpCnt > 2 and inpCnt % 2 == 1:
        if netlistReduceMuxToShift(builder, n, worklist, removed):
            return True

    return False
