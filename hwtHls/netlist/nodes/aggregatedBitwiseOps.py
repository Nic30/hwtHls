from copy import copy
from typing import List, Dict, Optional, Generator, Callable, Union, Tuple

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.nodes.aggregate import \
    HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregateTmpForScheduling
from hwtHls.netlist.nodes.node import HlsNetNode_numberForEachInput, \
    HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.schedulableNode import OutputTimeGetter, OutputMinUseTimeGetter, \
    SchedTime
from hwtHls.netlist.scheduler.clk_math import clkWindowBeginOfNext
from hwtHls.netlist.scheduler.errors import TimeConstraintError
from hwtHls.netlist.techmap.hlsNetlistToCppTranslator import HlsNetlistToCppTranslator
from hwtHls.netlist.techmap.techmap import FlowmapWorker, HlsNetNode as HlsNetNodeCpp, scheduleLutAlap
from hwtHls.platform.opRealizationMeta import OpRealizationMeta


class HlsNetNodeBitwiseOps(HlsNetNodeAggregateTmpForScheduling):
    """
    Container of cluster of bitwise operators.

    :ivar _totalInputCnt: the dictionary mapping the nodes of cluster to a number of transitive inputs
        from outside of cluster. Used to approximate latency of an operand tree.
    """

    def __init__(self, netlist:"HlsNetlistCtx", subNodes: List[HlsNetNode], name:str=None):
        HlsNetNodeAggregateTmpForScheduling.__init__(self, netlist, subNodes, name=name)
        self._totalInputCnt: Dict[HlsNetNodeOperator, int] = {}
        self._toCppTranslator:Optional[HlsNetlistToCppTranslator] = None
        self._flowMapWorker: Optional[FlowmapWorker] = None

    @staticmethod
    def _resolveSubnodeRealization_normalizeTiming(node: HlsNetNodeOperator, wireDelay: Union[float, Tuple[float]]):
        if not isinstance(wireDelay, (int, float)):
            wireDelay = wireDelay[0]

        return HlsNetNode_numberForEachInput(node, wireDelay)

    def _createAdhocRealizationIfPlatformDoesNotProvideMultiClockImpl(self, bit_length:int):
        # platform does not support such wide multiclock operand, we have to create multi clock
        # realization ourselfs
        r = self.netlist.platform.get_op_realization(
            HwtOps.AND, None, bit_length, 2, self.netlist.realTimeClkPeriod)
        r = r.mutated(inputWireDelay=0,
                      outputWireDelay=r.inputWireDelay + r.outputWireDelay,
                      isMulticlock=True,)
        return r

    def resolveSubnodeRealization(self, node: HlsNetNodeOperator, input_cnt: int):
        netlist = self.netlist
        assert isinstance(node, HlsNetNodeOperator), node
        bit_length = node._outputs[0]._dtype.bit_length()

        # if node.operator is HwtOps.TERNARY:
        #     input_cnt = max(1, input_cnt // 2)

        representativeOperator = HwtOps.NOT if input_cnt == 1 else HwtOps.AND
        try:
            rWithThisNode = netlist.platform.get_op_realization(
                representativeOperator, None, bit_length,
                input_cnt, netlist.realTimeClkPeriod)
        except TimeConstraintError:
            rWithThisNode = self._createAdhocRealizationIfPlatformDoesNotProvideMultiClockImpl(bit_length)

        inputWireDelay = rWithThisNode.inputWireDelay
        inputClkTickOffset = rWithThisNode.inputClkTickOffset
        if input_cnt <= 2:
            if isinstance(inputWireDelay, tuple):
                inputWireDelay = tuple(inputWireDelay[0] for _ in node._inputs)

            if isinstance(inputClkTickOffset, tuple):
                inputClkTickOffset = tuple(
                    inputClkTickOffset[0] for _ in node._inputs)

            rWithThisNode.mutated(inputWireDelay=inputWireDelay, inputClkTickOffset=inputClkTickOffset)
            node.assignRealization(rWithThisNode)  # the first operator in cluster does not need any latency modifications
            return

        representativeOperatorForChildren = HwtOps.NOT if input_cnt - 2 == 1 else HwtOps.AND

        try:
            rWithoutThisNode = netlist.platform.get_op_realization(
                representativeOperatorForChildren, None, bit_length,
                input_cnt - 2, netlist.realTimeClkPeriod)
        except TimeConstraintError:
            rWithoutThisNode = self._createAdhocRealizationIfPlatformDoesNotProvideMultiClockImpl(bit_length)

        # substract the latency which is counted in some input latency
        inputClkTickOffset = rWithThisNode.inputClkTickOffset
        if not isinstance(inputClkTickOffset, int):
            inputClkTickOffset = inputClkTickOffset[:2]

        inputWireDelay_with = self._resolveSubnodeRealization_normalizeTiming(node, rWithThisNode.inputWireDelay)
        inputWireDelay_without = self._resolveSubnodeRealization_normalizeTiming(node, rWithoutThisNode.inputWireDelay)
        inDelay = max((inputWireDelay_with[0] - inputWireDelay_without[0], 0))
        inputWireDelay = tuple(inDelay for _ in node._inputs)
            # max((latWith - latWithout, 0))
            # for latWith, latWithout in zip(inputWireDelay_with, inputWireDelay_without)

        if isinstance(inputClkTickOffset, tuple):
            inputClkTickOffset = tuple(
                inputClkTickOffset[0] for _ in node._inputs)

        rWithThisNode.mutated(inputWireDelay=inputWireDelay, inputClkTickOffset=inputClkTickOffset)
        node.assignRealization(rWithThisNode)

    def scheduleAsapWithQuantization(self, node: HlsNetNodeOperator,
                                    pathForDebug: Optional[SetList["HlsNetNode"]],
                                    beginOfFirstClk: SchedTime,
                                    outputTimeGetter: Optional[OutputTimeGetter]):
        assert node in self.subNodes, (node, self.subNodes)
        if node.scheduledOut is None:
            if pathForDebug is not None:
                if node in pathForDebug:
                    raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(node):]])
                else:
                    pathForDebug.append(node)
            try:
                if isinstance(node, HlsNetNodeAggregatePortIn):
                    node.scheduleAsap(pathForDebug, beginOfFirstClk, outputTimeGetter)
                    totalInputCnt = 1
                    self._totalInputCnt[node] = totalInputCnt
                else:
                    totalInputCnt = 0
                    inputAvailableTimes = []
                    for d in node.dependsOn:
                        obj = d.obj
                        # resolve time for something in this cluster
                        _sch, _inp_cnt = self.scheduleAsapWithQuantization(obj, pathForDebug, beginOfFirstClk, outputTimeGetter)
                        t = _sch[d.out_i]  # + epsilon
                        totalInputCnt += _inp_cnt
                        inputAvailableTimes.append(t)

                    self._totalInputCnt[node] = totalInputCnt
                    self.resolveSubnodeRealization(node, totalInputCnt)
                    # now we have times when the value is available on input
                    # and we must resolve the minimal time so each input timing constraints are satisfied

                    nodeZeroTime = 0
                    netlist = self.netlist
                    clkPeriod = netlist.normalizedClkPeriod
                    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
                    requiredForOutputTime = max(node.outputWireDelay) + ffdelay
                    for (availableInTime, inWireLatency, inputClkTickOffset) in zip(inputAvailableTimes, node.inputWireDelay, node.inputClkTickOffset):
                        assert inputClkTickOffset == 0
                        newNodeZeroTime = node._scheduleAsap_ScheduledZero_fromInSchedule(
                            availableInTime, inWireLatency, inputClkTickOffset, requiredForOutputTime, ffdelay)
                        if newNodeZeroTime > nodeZeroTime:
                            nodeZeroTime = newNodeZeroTime

                    if node.isMulticlock:
                        # :note: this was used only to mark that the node must be in next cycle
                        r = node.realization.mutated(isMulticlock=False)
                        node.assignRealization(r)

                    node._setScheduleZeroTimeSingleClock(nodeZeroTime)

                    for ot in node.scheduledOut:
                        if node.isMulticlock:
                            continue
                        for it in node.scheduledIn:
                            assert int(ot // clkPeriod) == int(it // clkPeriod), ("Bitwise operator primitives can not cross clock boundaries", node, it, ot, clkPeriod)
            finally:
                if pathForDebug is not None:
                    pathForDebug.pop()

        else:
            try:
                totalInputCnt = self._totalInputCnt[node]
            except KeyError:
                raise AssertionError(self, node, "Has missing totalInputCnt but has scheduledOut specified.")

        return node.scheduledOut, totalInputCnt

    @override
    def scheduleAsap(self,
                     pathForDebug: Optional[SetList["HlsNetNode"]],
                     beginOfFirstClk: SchedTime,
                     outputTimeGetter: Optional[OutputTimeGetter]) -> List[int]:
        """
        Incrementally stack operands to a larger tree and approximate the latency of the hypothetical mapping to LUT
        based on the number of the inputs of the tree.
        """
        if self.scheduledZero is None:
            if pathForDebug is not None:
                if self in pathForDebug:
                    raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                else:
                    pathForDebug.append(self)
            try:
                assert self._inputsInside, self
                assert self._outputsInside, self

                for o in self._outputsInside:
                    o: HlsNetNodeAggregatePortOut
                    scheduledOut, _ = self.scheduleAsapWithQuantization(o.dependsOn[0].obj, pathForDebug, beginOfFirstClk, outputTimeGetter)
                    o._setScheduleZero(scheduledOut[0])

                self.scheduledIn = tuple(i.scheduledOut[0] for i in self._inputsInside)
                self.scheduledZero = max(self.scheduledIn)
                self.scheduledOut = tuple(o.scheduledIn[0] for o in self._outputsInside)
            finally:
                if pathForDebug is not None:
                    pathForDebug.pop()

            # self.checkScheduling()
        # else:
        #    # :note: checkScheduling call duplicated so error stack trace show
        #    self.checkScheduling()

        return self.scheduledOut

    # def scheduleAlapCompactionForOutput(self,
    #                                    internalOut: HlsNetNodeOut,
    #                                    clkBoundaryTime: SchedTime,
    #                                    currentInputs: set[HlsNetNodeIn],
    #                                    outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
    #                                    excludeNode: Optional[Callable[[HlsNetNode], bool]]):
    #    """
    #    BFS consume all inputs until the start or until the boundary is found
    #
    #    :param internalOut: Internal output with known scheduling time.
    #                        (Time is known if all uses of this output have known time)
    #    The problem is is that we need to track number of unique primary inputs for each output.
    #    In order to do so the currentInputs is used.
    #    The problem is that each output may be used anywhere in other primary output cones that implies
    #    that for each node there are scheduling constraints derived from:
    #     * constraints of primary in/out ports
    #     * the number or input of currently selected tree
    #     * the timing constraints from scheduling for a different primary output
    #    """
    #    assert internalOut.obj.scheduledOut, (internalOut, "This function should be called only on scheduled nodes.")
    #    currentInputs.update(internalOut.obj._inputs)
    #    netlist = self.netlist
    #    ffdelay = netlist.platform.get_ff_store_time(
    #        netlist.realTimeClkPeriod, netlist.scheduler.resolution)
    #    clkPeriod = netlist.normalizedClkPeriod
    #    # 1. resolve which nodes we can add to cluster because they have all successors scheduled
    #    #    and adding it will not cause time to overflow clkBoundaryTime
    #    for dep in internalOut.obj.dependsOn:
    #        # get first time when dep is used
    #        depObj: HlsNetNode = dep.obj
    #        if depObj.scheduledOut is not None:
    #            for _dep in internalOut.obj.dependsOn:
    #                assert _dep.obj.realization is not None, (internalOut, _dep)
    #                assert _dep.obj.scheduledOut is not None, (internalOut, _dep)
    #            break  # this node was scheduled when some user node consumed it to layer of LUTs
    #            # assert depObj.scheduledOut is None, (internalOut, depObj, "Must not be scheduled because its successor (internalOut.obj) is not scheduled yet")
    #
    #        assert depObj.realization is not None, (depObj, "realization should be resolved in ASAP")
    #        depT = None
    #        for idou in depObj.usedBy[dep.out_i]:
    #            idou: HlsNetNodeIn
    #            if idou.obj.scheduledIn is None:
    #                # dependency has some other use which was not yet seen we have to wait until it is resolved
    #                depT = inf
    #                break
    #
    #            else:
    #                t = idou.obj.scheduledIn[idou.in_i]
    #                if depT is None:
    #                    depT = t
    #                else:
    #                    depT = min(depT, t)
    #
    #        if depT is not None and math.isinf(depT):
    #            continue
    #
    #        # check if dependency has some other uses which are affecting the schedule
    #
    #        isInPort = isinstance(depObj, HlsNetNodeAggregatePortIn)
    #        if isInPort:
    #            depT = self._getAlapOutsideOutMinUseTime(depObj, clkBoundaryTime, depT, outputMinUseTimeGetter, excludeNode)
    #        elif outputMinUseTimeGetter is not None:
    #            depT = outputMinUseTimeGetter(dep, depT)
    #
    #        if depT is not None:
    #            # if time of this dependency can be resolved, set its schedule and continue scheduling there
    #            assert depObj.scheduledOut is None or depObj.scheduledOut[0] == depT, (
    #                "The node was not supposed to be scheduled because we should not see this use of this output yet",
    #                dep, depT, depObj.scheduledOut[0])
    #            assert len(depObj._outputs) == 1, (depObj._outputs, "Only operators with a single output expected")
    #            if not isInPort:
    #                self.resolveSubnodeRealization(depObj, len(currentInputs) + len(depObj._inputs))
    #
    #            if isInPort:
    #                if depT != depObj.scheduledZero:
    #                    depObj._setScheduleZeroTimeSingleClock(depT)
    #
    #            elif depT - depObj.inputWireDelay[0] <= clkBoundaryTime:
    #                # can not fit this node inside current clock cycle
    #                newClkBeginBoundary = clkWindowBeginForTime(depT, clkPeriod)
    #                # move to start of clock cycle - ffdealy
    #                depObj._setScheduleZeroTimeSingleClock(min(clkBoundaryTime - ffdelay, depT))
    #                # all uses known and time crossing clock boundary, start a new cluster from this output
    #                self.scheduleAlapCompactionForOutput(
    #                    dep, newClkBeginBoundary,
    #                    set(), outputMinUseTimeGetter, excludeNode)
    #            else:
    #                # somewhere inside clock cycle, no need to modify time
    #                depObj._setScheduleZeroTimeSingleClock(depT)
    #                self.scheduleAlapCompactionForOutput(
    #                    dep, clkBoundaryTime,
    #                    currentInputs, outputMinUseTimeGetter, excludeNode)

    # @override
    # def scheduleAlapCompaction(self,
    #                           endOfLastClk: SchedTime,
    #                           outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
    #                           excludeNode: Optional[Callable[[HlsNetNode], bool]]) -> Generator["HlsNetNode", None, None]:
    #    """
    #    1. Resolve ALAP times for all inputs outside of this node where outputs are connected.
    #       Note that this time is not the output time of internal output because output value may be required sooner.
    #       * The total delay of subgraph is specified by number of inputs.
    #       * The graph is cut on clock period boundaries.
    #       * The problem is that we know the latency once we know the number of inputs, but we need a latency in order
    #         to find out when the graph should be cut due to clock period boundary and from there we know the number of inputs.
    #       * Problem is that we do not know which output is most constraining.
    #    2. For each sub node perform ALAP compaction.
    #       Use external output times a starting points. For each output we have to count inputs from clock boundary
    #       so we can resolve the latency of the operator tree.
    #    3. Store in/out schedule of children to this parent node.
    #    """
    #    # :note: There must be at least a single output which is not used internally in the cluster
    #    #        because cluster node graph is cycle free
    #    netlist = self.netlist
    #    clkPeriod = netlist.normalizedClkPeriod
    #    ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
    #    originalSchedule = {}
    #    self.copyScheduling(originalSchedule)
    #    scheduledZero = self.scheduledZero
    #    scheduledIn = self.scheduledIn
    #    scheduledOut = self.scheduledOut
    #
    #    self.resetScheduling()
    #    for oPort in self._outputsInside:
    #        assert not any(
    #            oPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter, excludeNode)
    #            ), (
    #            oPort, "Should only copy times from uses")
    #
    #    for outerO, oPort in zip(self._outputs, self._outputsInside):
    #        o: HlsNetNodeOut = oPort.dependsOn[0]
    #        insideClusterUses = o.obj.usedBy[o.out_i]
    #        if len(insideClusterUses) != 1:
    #            # run only if driver of this output is connected to node which is connected
    #            # sorely to this output (otherwise this will run as a part of parent expression)
    #            continue
    #
    #        if o.obj.scheduledOut is not None:
    #            # output is scheduled, this may happen if some other port translated
    #            # some expression which is subexpression of "o"
    #            continue
    #
    #        assert insideClusterUses[0] is oPort._inputs[0], (oPort, insideClusterUses)
    #        # this is just output to outside, copy timing from outside input
    #        t = oPort.scheduledIn[0]
    #        if outputMinUseTimeGetter is not None:
    #            t = outputMinUseTimeGetter(outerO, t)
    #
    #        assert len(o.obj.usedBy) == 1, ("Should be only bitwise operator with a single output", o)
    #        self.resolveSubnodeRealization(o.obj, len(o.obj._inputs))
    #        clkStartBoundary = clkWindowBeginForTime(t, clkPeriod)
    #        if t - o.obj.inputWireDelay[0] <= clkStartBoundary:
    #            t = clkStartBoundary - ffdelay
    #            clkStartBoundary -= clkPeriod
    #
    #        o.obj._setScheduleZeroTimeSingleClock(t)
    #
    #        # set time for all dependencies in this cluster as last as possible
    #        self.scheduleAlapCompactionForOutput(o,
    #                                             clkStartBoundary,
    #                                             set(),
    #                                             outputMinUseTimeGetter,
    #                                             excludeNode)
    #
    #    self.copySchedulingFromChildren()
    #    selfOriginalScheduledIn = originalSchedule[self][1]
    #    for inI, (inT, dep) in enumerate(zip(self.scheduledIn, self.dependsOn)):
    #        depOutT = dep.obj.scheduledOut[dep.out_i]
    #        if inT < depOutT:
    #            # scheduling failed to meet timing requirements on at least one input
    #            # this node can not be moved and must stay as it was
    #            assert selfOriginalScheduledIn[inI] <= depOutT, (
    #                "The original schedule is also incorrect", self._id, depOutT, "->", selfOriginalScheduledIn[inI], dep)
    #            self.setScheduling(originalSchedule)
    #            return
    #
    #    # self.checkScheduling()
    #
    #    if self.scheduledZero != scheduledZero or self.scheduledIn != scheduledIn or self.scheduledOut != scheduledOut:
    #        for dep in self.dependsOn:
    #            yield dep.obj
    #

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]) -> Generator["HlsNetNode", None, None]:
        netlist = self.netlist
        assert abs(endOfLastClk % netlist.normalizedClkPeriod) == 0, (endOfLastClk, netlist.normalizedClkPeriod)
        for inI, (inT, dep) in enumerate(zip(self.scheduledIn, self.dependsOn)):
            depOutT = dep.obj.scheduledOut[dep.out_i]
            # scheduling failed to meet timing requirements on at least one input
            # this node can not be moved and must stay as it was
            assert inT >= depOutT, (
                "The original schedule is also incorrect", self._id,
                    depOutT, "->", inT, dep)

        originalSchedule = {}
        self.copyScheduling(originalSchedule)
        scheduledIn = self.scheduledIn
        scheduledOut = self.scheduledOut
        isAllowedInFFStoreTime = False if self.realization is None else self.realization.isAllowedInFFStoreTime
        endOfLastClkWithoutFF = endOfLastClk
        if not isAllowedInFFStoreTime:
            ffdelay = netlist.platform.get_ff_store_time(
                netlist.realTimeClkPeriod, netlist.scheduler.resolution)
            endOfLastClkWithoutFF -= ffdelay

        self.resetScheduling()
        for oPort in self._outputsInside:
            assert not any(
                oPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter, excludeNode)
                ), (
                oPort, "Should only copy times from uses")

        newScheduledOut0 = tuple(o.scheduledIn[0] for o in self._outputsInside)
        tr = self._toCppTranslator
        # print("scheduleAlapCompaction", self)
        somePrimaryOutWasMovedByEndOfLastClk = False
        if tr is None:
            for n in self._outputsInside:
                if n.scheduledZero > endOfLastClk:
                    # if the primary output is behind the boundary, we have to shift its schedule to be within boundary
                    n._setScheduleZeroTimeSingleClock(endOfLastClkWithoutFF)
                    somePrimaryOutWasMovedByEndOfLastClk = True

            tr = HlsNetlistToCppTranslator(netlist.normalizedClkPeriod, netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution))
            self._toCppTranslator = tr
            tr.translate(self.subNodes, SetList(self._inputsInside), SetList(self._outputsInside))
            nodes = []
            inputs = []
            outputs = []
            for n in self.subNodes:
                nCpp = tr.nodeMap[n]
                if isinstance(n, HlsNetNodeAggregatePortIn):
                    inputs.append(nCpp)
                elif isinstance(n, HlsNetNodeAggregatePortOut):
                    outputs.append(nCpp)
                nodes.append(nCpp)

            # print([n._id for n in nodes])
            # print([n._id for n in inputs])
            # print([(n._id, n.scheduledZero) for n in outputs])
            #
            fmw = FlowmapWorker(nodes, inputs, outputs,
                                order=netlist.platform.get_lut_inputs_max())
            self._flowMapWorker = fmw
        else:
            # :note: the nodes and their connections are expected to be still the same as when HlsNetlistToCppTranslator/FlowmapWorker was created
            assert len(tr.nodeOrdered) == len(self.subNodes), self
            assert len(tr.inputs) == len(self._inputsInside), self
            assert len(tr.outputs) == len(self._outputsInside), self

            nodeMap = tr.nodeMap
            for n in tr.nodeOrdered:
                nCpp: HlsNetNodeCpp = nodeMap[n]
                if isinstance(n, HlsNetNodeAggregatePortOut):
                    if n.scheduledZero > endOfLastClk:
                        # if the primary output is behind the boundary, we have to shift its schedule to be within boundary
                        n._setScheduleZeroTimeSingleClock(endOfLastClkWithoutFF)
                        somePrimaryOutWasMovedByEndOfLastClk = True
                    tr.copySchedulingPyToCppOfNode(n, nCpp)
                else:
                    nCpp.scheduledZero = None

            fmw = self._flowMapWorker
            fmw.reset()

        fmw.label_nodes()
        fmw.map_luts()
        # print("luts", {k._id: sorted(n._id for n in lutGates) for k, lutGates in fmw.lut_gates.items()})
        lutDelay: SchedTime = netlist.platform.get_lut_dealy_max_normalized(netlist.realTimeClkPeriod, netlist.scheduler.resolution)
        # cppToPy: dict[HlsNetNodeCpp, HlsNetNode] = {tr.nodeMap[n]: n for n in tr.nodeOrdered}
        # toGraphviz = HwtHlsNetlistLutToGraphviz("test", fmw.lut_nodes, fmw.lut_gates, cppToPy)
        # toGraphviz.construct()
        # with open(f"tmp/test.{self._id:d}.lut.dot", "w") as out:
        #     out.write(toGraphviz.dumps())
        scheduleLutAlap(fmw, lutDelay, endOfLastClk)
        # print("scheduled", self._id)
        # toGraphviz = HwtHlsNetlistLutToGraphviz("test", fmw.lut_nodes, fmw.lut_gates, cppToPy)
        # toGraphviz.construct()
        # with open(f"tmp/test.{self._id:d}.alap.dot", "w") as out:
        #    out.write(toGraphviz.dumps())
        tr.copySchedulingCppToPy()
        newScheduledOut1 = tuple(o.scheduledIn[0] for o in self._outputsInside)
        for outI, (t, newT) in enumerate(zip(newScheduledOut0, newScheduledOut1)):
            assert newT <= t, (self, outI, t, newT, "alap time for output can not"
                               " be later than its earliest external use")
        self.copySchedulingFromChildren()
        # print("scheduled", self.scheduledIn, self.scheduledOut)
        selfOriginalScheduledIn = originalSchedule[self][1]
        tracer = netlist.scheduler._dbgTracer
        for inI, (inT, dep) in enumerate(zip(self.scheduledIn, self.dependsOn)):
            depOutT = dep.obj.scheduledOut[dep.out_i]
            if inT < depOutT:
                # scheduling failed to meet timing requirements on at least one input
                # this node can not be moved and must stay as it was
                assert selfOriginalScheduledIn[inI] >= depOutT, (
                    "The original schedule is also incorrect", self._id,
                    depOutT, "->", selfOriginalScheduledIn[inI], dep)
                if somePrimaryOutWasMovedByEndOfLastClk:
                    if tracer is not None:
                        tracer.log((self, "unchedulable for endOfLastClk"))
                    raise TimeConstraintError(
                        "The time between primary inputs and endOfLastClk is too short",
                        self, endOfLastClk)

                self.setScheduling(originalSchedule)
                self.copySchedulingFromChildren()
                if tracer is not None:
                    tracer.log((self, "restoring"))
                # self.checkScheduling()
                return

        # self.checkScheduling()

        if self.scheduledIn != scheduledIn or self.scheduledOut != scheduledOut:
            for dep in self.dependsOn:
                yield dep.obj

