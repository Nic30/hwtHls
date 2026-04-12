from functools import lru_cache
from math import ceil
from typing import Literal, Optional

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.hdl.types.bits import HBits
from hwt.pyUtils.arrayQuery import grouper, balanced_reduce
from hwt.pyUtils.setList import SetList
from hwtHls.architecture.componentGenerator import ComponentGenerator
from hwtHls.netlist.builder import HlsNetlistBuilderWithWorklist
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.netlist.transformation.simplifyUtilsHierarchyAware import disconnectAllInputs
from hwtHls.platform.opRealizationMeta import OpRealizationMeta, \
    EMPTY_OP_REALIZATION


class ComponentGeneratorICMP_EQ_NE(ComponentGenerator):
    """
    Component generator for ICMP EQ/NE with support for pipelining
    """

    def __init__(self, platform: "DefaultHlsPlatform", genNamePrefix:str, moduleName:str, predicate: Literal[HwtOps.EQ, HwtOps.NE]):
        ComponentGenerator.__init__(self, platform, genNamePrefix, moduleName)
        self.predicate = predicate
        # op, datawidth -> layers of operators and width at which they are performed, flag signalizing that one of operands is constant
        # eg. 16b ICMP_EQ is split to ((EQ, 8), (AND, 2)) if frequency is limiting eq width to just 8b
        self.schedulingCache: dict[tuple[HOperatorDef, int], tuple[OpRealizationMeta, tuple[tuple[HOperatorDef, int, OpRealizationMeta], ...]]]

    @staticmethod
    def _getSchedulingCacheKey(node: HlsNetNodeOperator):
        bit_length = node.dependsOn[0]._dtype.bit_length()
        # cmp with constant is as fast as half sized cmp
        atleasOneOpIsConst = sum(int(isinstance(dep.obj, HlsNetNodeConst)) for dep in node.dependsOn) > 0
        return (node.operator, bit_length, atleasOneOpIsConst)

    def resolveRealizationOfNode(self, node: "HlsNetNode") -> None:
        cacheKey = self._getSchedulingCacheKey(node)
        try:
            self.schedulingCache[cacheKey]
        except KeyError:
            pass

        netlist = node.netlist
        assert self.platform is netlist.platform
        platform = self.platform
        assert len(node.dependsOn) == 2
        op, bit_length, oneOpIsConst = cacheKey
        # if one operand is constant the constant operand is hardcoded into LUT and
        # thus hlaf of the input bits is actually requered
        representatinveBitLength = ceil(bit_length / 2) if oneOpIsConst else bit_length
        schedResolution: float = netlist.scheduler.resolution
        ffdelay: SchedTime = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, schedResolution)
        clkWindowBudget: SchedTime = netlist.normalizedClkPeriod - ffdelay

        try:
            r = platform.get_op_realization(
                node.operator, node.operatorSpecialization,
                representatinveBitLength, 2, netlist.realTimeClkPeriod)
            if not r.fitsIntoSchedTime(clkWindowBudget, schedResolution):
                r = None
                raise TimeConstraintError()
        except TimeConstraintError as e:
            # this means that without pipelining this operator can not meet frequency requirements
            r = None
            lutInputs = self.platform.get_lut_inputs_max()
            if representatinveBitLength <= lutInputs:
                raise TimeConstraintError(*e.args, self.operator, self._id, "even the smallest possible part is too slow")

        if r is None:
            # find out the largest operator which satisfies the timing
            # prefer widths which are multiple of LUT inputs,
            maxFirstLevelWidth, firstLevelR = self._getMaxCmpOpInputForClk(oneOpIsConst, clkWindowBudget, schedResolution, node)
            firstLevelR: OpRealizationMeta
            assert maxFirstLevelWidth < bit_length
            # decide how to pipeline this operator
            if self.predicate == HwtOps.EQ:
                mergeOperator = HwtOps.AND
            else:
                assert self.predicate == HwtOps.NE, self.predicate
                mergeOperator = HwtOps.OR
            maxMergeLogicInputs, lastMergeLogicR = self._getMaxLogicOpInputsForClk(mergeOperator, netlist.realTimeClkPeriod,
                                                                                   schedResolution, clkWindowBudget)
            layers = [(op, maxFirstLevelWidth, firstLevelR), ]
            w = maxFirstLevelWidth
            totalInputWidth = bit_length if oneOpIsConst else bit_length * 2
            while True:
                # check how many input should the merging logic have
                requestedMergeLogicInputs = ceil(totalInputWidth / w)
                if requestedMergeLogicInputs < maxMergeLogicInputs:
                    lastMergeLogicR = self.platform.get_op_realization(
                        mergeOperator, None, 1, requestedMergeLogicInputs, netlist.realTimeClkPeriod)
                    layers.append((mergeOperator, requestedMergeLogicInputs, lastMergeLogicR))
                    break
                else:
                    layers.append((mergeOperator, maxMergeLogicInputs, lastMergeLogicR))
                    if requestedMergeLogicInputs == maxMergeLogicInputs:
                        break

                w *= maxMergeLogicInputs
            assert firstLevelR.fitsIntoSingleClockWindow()
            assert lastMergeLogicR.fitsIntoSingleClockWindow()
            r = OpRealizationMeta(inputWireDelay=firstLevelR.inputWireDelay + firstLevelR.outputWireDelay,
                                  outputWireDelay=lastMergeLogicR.inputWireDelay + lastMergeLogicR.outputWireDelay,
                                  outputClkTickOffset=len(layers) - 1,
                                  isMulticlock=True)
            assert r.inputWireDelay / schedResolution < clkWindowBudget, (r.inputWireDelay / schedResolution, clkWindowBudget)
            assert r.outputWireDelay / schedResolution < clkWindowBudget, (r.outputWireDelay / schedResolution, clkWindowBudget)
        else:
            layers = [(node.operator, bit_length, r), ]
        self.schedulingCache[cacheKey] = (r, layers)
        return r

    # @lru_cache
    def _getMaxCmpOpInputForClk(self, oneOpIsConst: bool, clkWindowBudget: SchedTime, schedResolution: float, node: HlsNetNodeOperator):
        lutInputs = self.platform.get_lut_inputs_max()
        firstLevelInputs = lutInputs
        if not oneOpIsConst:
            if lutInputs & 1:
                firstLevelInputs -= 1  # round to multiple of 2

        platform = self.platform
        netlist = node.netlist
        w = firstLevelInputs
        assert lutInputs > 1
        r = None
        while True:
            wIncreased = w * lutInputs
            try:
                _r: OpRealizationMeta = platform.get_op_realization(
                    node.operator, node.operatorSpecialization,
                    ceil(wIncreased / 2) if oneOpIsConst else wIncreased, 2, netlist.realTimeClkPeriod)
                if not _r.fitsIntoSchedTime(clkWindowBudget, schedResolution):
                    break
                r = _r
            except TimeConstraintError:
                # wIncreased is too slow, we found the largest posible width
                break
            w = wIncreased

        if r is None:
            # case that the first increase does not fit
            r: OpRealizationMeta = platform.get_op_realization(
                    node.operator, node.operatorSpecialization,
                    ceil(w / 2) if oneOpIsConst else w, 2, netlist.realTimeClkPeriod)
            if not r.fitsIntoSchedTime(clkWindowBudget, schedResolution):
                raise TimeConstraintError("Clock period too low even for smallest part of operator, can not pipeline",
                                  node, r.inputWireDelay / schedResolution, clkWindowBudget)

        return w, r

    # @lru_cache
    def _getMaxLogicOpInputsForClk(self, operator: HOperatorDef, realTimeClkPeriod: float, schedResolution: float, clkWindowBudget: SchedTime) -> tuple[int, OpRealizationMeta]:
        lutInputs = self.platform.get_lut_inputs_max()
        maxMergeLogicInputs = lutInputs
        r = None
        while True:
            wIncreased = maxMergeLogicInputs * lutInputs
            if wIncreased >= (1 << 64):
                # exit because delay of logic op itself is not limiting factor there for this clok frequency
                break
            try:
                _r = self.platform.get_op_realization(
                    operator, None, 1, wIncreased, realTimeClkPeriod)
                if not _r.fitsIntoSchedTime(clkWindowBudget, schedResolution):
                    break
                r = _r
            except TimeConstraintError:
                # wIncreased is too slow, we found the largest posible width
                break
            maxMergeLogicInputs = wIncreased

        if r is None:
            # case that the first increase does not fit
            r = self.platform.get_op_realization(
                    operator, None, 1, maxMergeLogicInputs, realTimeClkPeriod)
            assert r.fitsIntoSchedTime(clkWindowBudget, schedResolution)

        return maxMergeLogicInputs, r

    def toHwtCompatibleOperatorAfterScheduling(self, node: "HlsNetNode", worklist: SetList["HlsNetNode"]) -> bool:
        cacheKey = self._getSchedulingCacheKey(node)
        cacheVal = self.schedulingCache.get(cacheKey)
        if cacheVal is None:
            assert node.realization is not None, node
            return False  # this is newly generated node which is known to fit
        r, layers = cacheVal
        if len(layers) == 1:
            return False

        netlist = node.netlist
        schedulerResolution: float = netlist.scheduler.resolution
        isFirst = True
        worklistTmp: list[HlsNetNode] = []
        inputWidth: int = node.dependsOn[0]._dtype.bit_length()
        builder: HlsNetlistBuilderWithWorklist = HlsNetlistBuilderWithWorklist(node.getHlsNetlistBuilder(), worklistTmp)
        inTime: SchedTime = node.scheduledIn[0]
        parent: ArchElement = node.getParent()
        nextLayerInputs: Optional[list[HlsNetNodeOut]] = None
        for op, widthStep, layerRealization in layers:
            op: HOperatorDef
            layerRealization: OpRealizationMeta
            if isFirst:
                clkI = inTime // netlist.normalizedClkPeriod
                assert op is self.predicate, op
                nextLayerInputs = []
                w = 0
                while w < inputWidth:
                    thisWidthStep = min(widthStep, inputWidth - w)
                    sliceResT = HBits(thisWidthStep)
                    # construct slices of original operands
                    o0, o1 = (builder.buildIndexConstSlice(sliceResT, dep, w + thisWidthStep, w) for dep in node.dependsOn)
                    for newNode in worklistTmp:
                        newNode: HlsNetNode
                        newNode.assignRealization(EMPTY_OP_REALIZATION)
                        newNode._setScheduleZeroTimeSingleClock(inTime)
                        parent._addNodeIntoScheduled(clkI, newNode, allowNewClockWindow=False)

                    worklist.extend(worklistTmp)
                    worklistTmp.clear()

                    # construct first level of partial cmp operands
                    if self.predicate is HwtOps.EQ:
                        cmp = builder.buildEq(o0, o1)
                    else:
                        assert self.predicate is HwtOps.NE
                        cmp = builder.buildNe(o0, o1)

                    for newNode in worklistTmp:
                        newNode: HlsNetNode
                        assert isinstance(newNode, HlsNetNodeOperator), newNode
                        newNode.assignRealization(layerRealization)
                        newNode._setScheduleZeroTimeSingleClock(inTime + SchedTime(layerRealization.inputWireDelay / schedulerResolution))
                        parent._addNodeIntoScheduled(clkI, newNode, allowNewClockWindow=False)
                    worklist.extend(worklistTmp)
                    worklistTmp.clear()

                    nextLayerInputs.append(cmp)
                    w += thisWidthStep
                isFirst = False
            else:
                clkI += 1
                inTime = clkI * netlist.normalizedClkPeriod
                # construct the level of result merging logic, for example for EQ use AND
                # binary reduce widthStep-bits of operands
                newNextLayerInputs: list[HlsNetNodeOut] = []
                for mergeInputs in grouper(widthStep, nextLayerInputs, NOT_SPECIFIED):
                    mergeInputs = tuple(mergeInputs)
                    v = balanced_reduce(mergeInputs, builder.buildAnd if op is HwtOps.AND else builder.buildOr)
                    # assing realization and time for top node
                    newNode: HlsNetNode = v.obj
                    assert isinstance(newNode, HlsNetNodeOperator), newNode
                    newNode.assignRealization(layerRealization)
                    newNode._setScheduleZeroTimeSingleClock(inTime + SchedTime(layerRealization.inputWireDelay / schedulerResolution))
                    parent._addNodeIntoScheduled(clkI, newNode, allowNewClockWindow=True)

                    # for other assign empty realization
                    for newNode in worklistTmp:
                        newNode: HlsNetNode
                        if newNode is v.obj:
                            assert v.obj.realization is not None
                            continue  # skip top node
                        assert newNode.realization is None, newNode
                        newNode.assignRealization(EMPTY_OP_REALIZATION)
                        newNode._setScheduleZeroTimeSingleClock(inTime)
                        parent._addNodeIntoScheduled(clkI, newNode, allowNewClockWindow=False)

                    newNextLayerInputs.append(v)
                    worklist.extend(worklistTmp)
                    worklistTmp.clear()

                nextLayerInputs = newNextLayerInputs

        # replace this node with newly generated ones
        assert len(nextLayerInputs) == 1
        newO = nextLayerInputs[0]
        netlist.dbgSubmoduleBuidTracer.log(("replacing with", newO, "pipeline:", layers))
        builder.replaceOutput(node._outputs[0], newO, True)
        disconnectAllInputs(node, worklist)
        node.markAsRemoved()
        return True

    def toRtlForNode(self, node: HlsNetNodeOperator, allocator: "ArchElement") -> None:
        cacheKey = self._getSchedulingCacheKey(node)
        cacheVal = self.schedulingCache.get(cacheKey)
        if cacheVal is not None:
            _, layers = self.schedulingCache[cacheKey]
            assert len(layers) == 1, ("Only non pipelined variants should get there, pipelined variant should have been lowered in toHwtCompatibleOperatorAfterScheduling", layers)
        return node._rtlAlloc_default(allocator)
        # else:
        #    layerValues: list[TimeIndependentRtlResourceItem] = []
        #    for (dep, t) in zip(self.dependsOn, self.scheduledIn):
        #        assert dep is not None, ("All inputs must be connected", self, self.dependsOn)
        #        _o = allocator.rtlAllocHlsNetNodeOutInTime(dep, t)
        #        assert isinstance(_o, TimeIndependentRtlResourceItem), (dep, _o)
        #        layerValues.append(_o)
        #    nextLayerValues: list[TimeIndependentRtlResourceItem] = []
        #    for isLast, (op, bitwidth) in enumerate(layers):
        #        raise NotImplementedError()
        #        if isLast:
        #            node._rtlAlloc_registerOutput(allocator, node._outputs[0], nextLayerValues[0])
        #    raise NotImplementedError()

