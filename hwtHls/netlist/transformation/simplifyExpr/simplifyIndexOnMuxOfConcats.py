from typing import Set, Tuple, List, Optional, Union, Sequence

from hwt.hdl.operatorDefs import AllOps
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.types.sliceVal import HSliceVal
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.mux import HlsNetNodeMux
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.transformation.simplifyExpr.simplifyMux import popConcatOfSlices
from hwtHls.netlist.transformation.simplifyUtils import getConstOfOutput, \
    replaceOperatorNodeWith
from hwt.hdl.types.defs import BIT

# value, low, high
BitChunkTuple = Union[HValue, Tuple[HlsNetNodeOut, int, int]]
CaseTuple = Tuple[List[BitChunkTuple], Optional[HlsNetNodeOut]]


def _buildConcatFromSliceTuples(builder: HlsNetlistBuilder, worklist: UniqList[HlsNetNode], vals: Sequence[BitChunkTuple]):
    assert vals
    valuesSliced = []
    for _v in vals:
        if isinstance(_v, HValue):
            valuesSliced.append(_v)
        else:
            (v, l, h) = _v
            vSliced = builder.buildIndexConst(Bits(h - l), v, h, l, worklist)
            valuesSliced.append(vSliced)
            worklist.append(vSliced.obj)

    return builder.buildConcat(*valuesSliced)


def _constructMuxOps(builder: HlsNetlistBuilder, caseTuples: Sequence[CaseTuple], worklist: UniqList[HlsNetNode])\
        ->List[Tuple[HlsNetNodeOut, Optional[HlsNetNodeOut]]]:
    muxOps = []
    for vals, c in caseTuples:
        assert vals
        valuesSliced = []
        for _v in vals:
            if isinstance(_v, HValue):
                valuesSliced.append(_v)
            else:
                (v, l, h) = _v
                vSliced = builder.buildIndexConst(Bits(h - l), v, h, l, worklist)
                valuesSliced.append(vSliced)
                worklist.append(vSliced.obj)

        caseConcat = builder.buildConcat(*valuesSliced)

        muxOps.append(caseConcat)
        if not isinstance(caseConcat, HValue):
            worklist.append(caseConcat.obj)
        if c is not None:
            muxOps.append(c)

    return tuple(muxOps)


def sliceOutValueFromValue(val: HValue, lowBitNo: int, highBitNo: int):
    if lowBitNo + 1 == highBitNo:
        v = val[lowBitNo]
        if v._dtype.force_vector:
            return v._reinterpret_cast(BIT)
        else:
            return v
    else:
        return val[highBitNo:lowBitNo]


def sliceOutValueFromConcatOrConst(v: HlsNetNodeOut,
                                   lowBitNo: int, highBitNo: int,
                                   collectLeftover: bool):
    width = v._dtype.bit_length()
    _leftover = [] if collectLeftover else None
    _extracted = []
    vObj = v.obj
    if isinstance(vObj, HlsNetNodeConst):
        vVal = vObj.val
        if collectLeftover and lowBitNo != 0:
            _leftover.append(sliceOutValueFromValue(vVal, 0, lowBitNo))

        _v = sliceOutValueFromValue(vVal, lowBitNo, highBitNo)
        if _v._dtype.force_vector:
            _v = sliceOutValueFromValue(vVal, lowBitNo, highBitNo)

        assert not _v._dtype.force_vector, (_v, lowBitNo, highBitNo)
        _extracted.append(_v)

        if collectLeftover and highBitNo != width:
            _v = sliceOutValueFromValue(vVal, highBitNo, width)
            _leftover.append(_v)

    elif isinstance(vObj, HlsNetNodeOperator) and vObj.operator == AllOps.CONCAT:
        offset = 0
        for o, l, h in popConcatOfSlices(v, depthLimit=1):
            w = h - l
            if offset < lowBitNo:
                if offset + w <= lowBitNo:
                    # no overlap with extracted part
                    if collectLeftover:
                        _leftover.append((o, l, h))
                    offset += w
                    continue
                else:
                    # overlap with beginning of extracted part, must split
                    bitsUtilExtractedStart = lowBitNo - offset
                    if collectLeftover:
                        _leftover.append((o, l, l + bitsUtilExtractedStart))
                    l += bitsUtilExtractedStart
                    w -= bitsUtilExtractedStart
                    offset += bitsUtilExtractedStart

            assert offset >= lowBitNo
            if offset < highBitNo:
                # overlap with extracted
                if offset + w >= highBitNo:
                    # overlap with leftover as well
                    bitUntilExtractedEnd = highBitNo - offset
                    _extracted.append((o, l, l + bitUntilExtractedEnd))
                    l += bitUntilExtractedEnd
                    w -= bitUntilExtractedEnd
                    offset += bitUntilExtractedEnd
                else:
                    _extracted.append((o, l, h))
                    l = h
                    offset += w

            if h != l:
                assert h > l
                if collectLeftover:
                    _leftover.append((o, l, h))
                offset += w

        assert sum(h - l for (_, l, h) in _extracted) == highBitNo - lowBitNo, (
            highBitNo - lowBitNo, _extracted)
        if collectLeftover:
            assert sum(h - l for (_, l, h) in _leftover) == width - (highBitNo - lowBitNo), (
                width - (highBitNo - lowBitNo), _leftover)
    else:
        return None, None

    return _extracted, _leftover


def sliceOrIndexToHighLowBitNo(index: Union[HSliceVal, BitsVal]):
    if isinstance(index, HSliceVal):
        assert int(index.val.step) == -1
        lowBitNo = int(index.val.stop)
        highBitNo = int(index.val.start)
    else:
        lowBitNo = int(index)
        highBitNo = lowBitNo + 1

    return highBitNo, lowBitNo


def netlistReduceIndexOnMuxOfConcats(n: HlsNetNodeOperator, worklist: UniqList[HlsNetNode], removed: Set[HlsNetNode]):
    assert n.operator == AllOps.INDEX, n

    index = getConstOfOutput(n.dependsOn[1])
    if index is None:
        return False  # non constant slice

    highBitNo, lowBitNo = sliceOrIndexToHighLowBitNo(index)

    inp = n.dependsOn[0]
    if not isinstance(inp.obj, HlsNetNodeMux):
        return False

    # # inp is used only by slices, and none of them overlaps with range defined by this slice index

    # val, condition
    extracted: List[CaseTuple] = []
    leftover: List[CaseTuple] = []
    width = inp.obj._outputs[0]._dtype.bit_length()
    if lowBitNo == 0 and highBitNo == width:
        return False  # the slice select whole mux

    worklist.append(n.dependsOn[1].obj)

    for v, c in  inp.obj._iterValueConditionDriverPairs():
        # if value it concat or const
        vObj = v.obj
        _extracted, _leftover = sliceOutValueFromConcatOrConst(v, lowBitNo, highBitNo, True)

        if _extracted is None:
            return False  # there is something else than just concatnt or concat in value, we can not split this mux

        leftover.append((_leftover, c))
        extracted.append((_extracted, c))
        worklist.append(vObj)

    builder: HlsNetlistBuilder = n.netlist.builder

    selfResT = n._outputs[0]._dtype
    extractedMuxOps = _constructMuxOps(builder, extracted, worklist)

    extractedO = builder.buildMux(selfResT, extractedMuxOps, name=n.name)
    replaceOperatorNodeWith(n, extractedO, worklist, removed)  # slice -> value extracted from mux
    worklist.append(extractedO.obj)

    # for rest of the users create a concatenation which will merge extracted and leftover value back
    if inp.obj.usedBy[inp.out_i]:
        leftoverMuxOps = _constructMuxOps(builder, leftover, worklist)
        leftoverO = builder.buildMux(Bits(inp._dtype.bit_length() - selfResT.bit_length()),
                                     leftoverMuxOps, name=inp.obj.name)
        worklist.append(leftoverO.obj)

        origConcatVals = []
        if lowBitNo != 0:
            leftoverSliced = builder.buildIndexConst(Bits(lowBitNo),
                                                          leftoverO,
                                                          lowBitNo, 0, worklist)
            origConcatVals.append(leftoverSliced)

        origConcatVals.append(extractedO)
        if highBitNo != width:
            extractedWidth = highBitNo - lowBitNo
            leftoverWidth = width - extractedWidth
            leftoverSliced = builder.buildIndexConst(Bits(leftoverWidth - lowBitNo),
                                                     leftoverO,
                                                     leftoverWidth, lowBitNo,
                                                     worklist)
            origConcatVals.append(leftoverSliced)

        worklist.extend(o.obj for o in origConcatVals)
        inpReplacement = builder.buildConcat(*origConcatVals)
        worklist.append(inpReplacement.obj)
        replaceOperatorNodeWith(inp.obj, inpReplacement, worklist, removed)

    return True

