from copy import copy
from math import inf
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
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import OutputTimeGetter, OutputMinUseTimeGetter, \
    SchedTime
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, \
    indexOfClkPeriod
from hwtHls.netlist.scheduler.errors import TimeConstraintError


class HlsNetNodeBitwiseOps(HlsNetNodeAggregateTmpForScheduling):
    """
    Container of cluster of bitwise operators.

    :ivar _totalInputCnt: the dictionary mapping the nodes of cluster to a number of transitive inputs
        from outside of cluster. Used to approximate latency of an operand tree.
    """

    def __init__(self, netlist:"HlsNetlistCtx", subNodes: List[HlsNetNode], name:str=None):
        HlsNetNodeAggregateTmpForScheduling.__init__(self, netlist, subNodes, name=name)
        self._totalInputCnt: Dict[HlsNetNodeOperator, int] = {}

    @staticmethod
    def _resolveSubnodeRealization_normalizeTiming(node: HlsNetNodeOperator, wireDelay: Union[float, Tuple[float]]):
        if not isinstance(wireDelay, (int, float)):
            wireDelay = wireDelay[0]

        return HlsNetNode_numberForEachInput(node, wireDelay)

    def resolveSubnodeRealization(self, node: HlsNetNodeOperator, input_cnt: int):
        netlist = self.netlist
        assert isinstance(node, HlsNetNodeOperator), node
        bit_length = node._outputs[0]._dtype.bit_length()

        # if node.operator is HwtOps.TERNARY:
        #    input_cnt = input_cnt // 2 + 1

        representativeOperator = HwtOps.NOT if input_cnt == 1 else HwtOps.AND
        rWithThisNode = netlist.platform.get_op_realization(
            representativeOperator, None, bit_length,
            input_cnt, netlist.realTimeClkPeriod)

        rWithThisNode = copy(rWithThisNode)
        if input_cnt <= 2:
            if isinstance(rWithThisNode.inputWireDelay, tuple):
                rWithThisNode.inputWireDelay = tuple(
                    rWithThisNode.inputWireDelay[0] for _ in node._inputs)
            if isinstance(rWithThisNode.inputClkTickOffset, tuple):
                rWithThisNode.inputClkTickOffset = tuple(
                    rWithThisNode.inputClkTickOffset[0] for _ in node._inputs)

            node.assignRealization(rWithThisNode)  # the first operator in cluster does not need any latency modifications
            return

        representativeOperatorForChildren = HwtOps.NOT if input_cnt - 2 == 1 else HwtOps.AND
        rWithoutThisNode = netlist.platform.get_op_realization(
            representativeOperatorForChildren, None, bit_length,
            input_cnt - 2, netlist.realTimeClkPeriod)

        # substract the latency which is counted in some input latency
        if not isinstance(rWithThisNode.inputClkTickOffset, int):
            rWithThisNode.inputClkTickOffset = rWithoutThisNode.inputClkTickOffset[:2]

        inputWireDelay_with = self._resolveSubnodeRealization_normalizeTiming(node, rWithThisNode.inputWireDelay)
        inputWireDelay_without = self._resolveSubnodeRealization_normalizeTiming(node, rWithoutThisNode.inputWireDelay)
        inDelay = max((inputWireDelay_with[0] - inputWireDelay_without[0], 0))
        rWithThisNode.inputWireDelay = tuple(inDelay for _ in node._inputs)
            # max((latWith - latWithout, 0))
            # for latWith, latWithout in zip(inputWireDelay_with, inputWireDelay_without)
        
        if isinstance(rWithThisNode.inputClkTickOffset, tuple):
            rWithThisNode.inputClkTickOffset = tuple(
                rWithThisNode.inputClkTickOffset[0] for _ in node._inputs)

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
                    clkPeriod = self.netlist.normalizedClkPeriod
                    for (available_in_time, in_delay, in_cycles) in zip(inputAvailableTimes, node.inputWireDelay, node.inputClkTickOffset):
                        assert in_cycles == 0
                        if in_delay >= clkPeriod:
                            raise TimeConstraintError(
                                "Impossible scheduling, clkPeriod too low for ",
                                node.inputWireDelay, node.outputWireDelay, node)

                        next_clk_time = start_of_next_clk_period(available_in_time, clkPeriod)
                        time_budget = next_clk_time - available_in_time

                        if in_delay >= time_budget:
                            available_in_time = next_clk_time

                        normalized_time = (available_in_time + in_delay)

                        if normalized_time > nodeZeroTime:
                            nodeZeroTime = normalized_time

                    node._setScheduleZeroTimeSingleClock(nodeZeroTime)
                    for ot in node.scheduledOut:
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
        if self.scheduledOut is None:
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
        self.checkScheduling()
        return self.scheduledOut

    def scheduleAlapCompactionForOutput(self,
                                        internalOut: HlsNetNodeOut,
                                        clkBoundaryTime: SchedTime,
                                        currentInputs: SetList[HlsNetNodeIn],
                                        outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                                        excludeNode: Optional[Callable[[HlsNetNode], bool]]):
        """
        BFS consume all inputs until the start or until the boundary is found

        :ivar internalOut: Internal output with known scheduling time. (Time is known if all uses of this output have known time)
        """
        assert internalOut.obj.scheduledOut, (internalOut, "This function should be called only on scheduled nodes.")
        currentInputs.extend(internalOut.obj._inputs)
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        clkPeriod = self.netlist.normalizedClkPeriod
        # 1. resolve which nodes we can add to cluster because they have all successors scheduled
        #    and adding it will not cause time to overflow clkBoundaryTime
        for dep in internalOut.obj.dependsOn:
            # get first time when dep is used
            depObj: HlsNetNode = dep.obj
            assert depObj.scheduledOut is None, (internalOut, depObj, "Must not be scheduled because its successor (internalOut.obj) is not scheduled yet")
            assert depObj.realization is not None, (depObj, "realization should be resolved in ASAP")
            depT = None
            for idou in depObj.usedBy[dep.out_i]:
                idou: HlsNetNodeIn
                if idou.obj.scheduledIn is None:
                    # dependency has some other use which was not yet seen we have to wait until it is resolved
                    depT = inf
                    break

                else:
                    t = idou.obj.scheduledIn[idou.in_i]
                    if depT is None:
                        depT = t
                    else:
                        depT = min(depT, t)

            if depT is inf:
                continue

            # check if dependency has some other uses which are affecting the schedule

            isInPort = isinstance(depObj, HlsNetNodeAggregatePortIn)
            if isInPort:
                depT = self._getAlapOutsideOutMinUseTime(depObj, clkBoundaryTime, depT, outputMinUseTimeGetter, excludeNode)
            elif outputMinUseTimeGetter is not None:
                depT = outputMinUseTimeGetter(dep, depT)

            if depT is not None:
                # if time of this dependency can be resolved, set its schedule and continue scheduling there
                assert depObj.scheduledOut is None or depObj.scheduledOut[0] == depT, (
                    "The node was not supposed to be scheduled because we should not see this use of this output yet",
                    dep, depT, depObj.scheduledOut[0])
                assert len(depObj._outputs) == 1, (depObj._outputs, "Only operators with a single output expected")
                if not isInPort:
                    self.resolveSubnodeRealization(depObj, len(currentInputs) + len(depObj._inputs))

                if isInPort:
                    if depT != depObj.scheduledZero:
                        depObj._setScheduleZeroTimeSingleClock(depT)

                elif depT - depObj.inputWireDelay[0] <= clkBoundaryTime:
                    # can not fit this node inside current clock cycle
                    newClkBeginBoundary = indexOfClkPeriod(depT, clkPeriod) * clkPeriod
                    depObj._setScheduleZeroTimeSingleClock(min(clkBoundaryTime - ffdelay, depT))  # move to start of clock cycle - ffdealy
                    # all uses known and time crossing clock boundary, start a new cluster from this output
                    self.scheduleAlapCompactionForOutput(dep, newClkBeginBoundary,
                                                             SetList(), outputMinUseTimeGetter, excludeNode)
                else:
                    # somewhere inside clock cycle, no need to modify time
                    depObj._setScheduleZeroTimeSingleClock(depT)
                    self.scheduleAlapCompactionForOutput(dep, clkBoundaryTime,
                                                             currentInputs, outputMinUseTimeGetter, excludeNode)

    @override
    def scheduleAlapCompaction(self,
                               endOfLastClk: SchedTime,
                               outputMinUseTimeGetter: Optional[OutputMinUseTimeGetter],
                               excludeNode: Optional[Callable[[HlsNetNode], bool]]) -> Generator["HlsNetNode", None, None]:
        """
        1. Resolve ALAP times for all inputs outside of this node where outputs are connected.
           Note that this time is not the output time of internal output because output value may be required sooner.
           * The total delay of subgraph is specified by number of inputs.
           * The graph is cut on clock period boundaries.
           * The problem is that we know the latency once we know the number of inputs, but we need a latency in order
             to find out when the graph should be cut due to clock period boundary and from there we know the number of inputs.
           * Problem is that we do not know which output is most constraining.
        2. For each sub node perform ALAP compaction.
           Use external output times a starting points. For each output we have to count inputs from clock boundary
           so we can resolve the latency of the operator tree.
        3. Store in/out schedule of children to this parent node.
        """
        # :note: There must be at least a single output which is not used internally in the cluster
        #        because cluster node graph is cycle free
        netlist = self.netlist
        clkPeriod = netlist.normalizedClkPeriod
        ffdelay = netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        originalSchedule = {}
        self.copyScheduling(originalSchedule)
        scheduledZero = self.scheduledZero
        scheduledIn = self.scheduledIn
        scheduledOut = self.scheduledOut

        self.resetScheduling()
        for oPort in self._outputsInside:
            assert not any(oPort.scheduleAlapCompaction(endOfLastClk, outputMinUseTimeGetter, excludeNode)), (
                oPort, "Should only copy times from uses")

        for outerO, oPort in zip(self._outputs, self._outputsInside):
            o: HlsNetNodeOut = oPort.dependsOn[0]
            insideClusterUses = o.obj.usedBy[o.out_i]
            if len(insideClusterUses) == 1:
                assert insideClusterUses[0] is oPort._inputs[0], (oPort, insideClusterUses)
                # this is just output to outside, copy timing from outside input
                t = oPort.scheduledIn[0]
                if outputMinUseTimeGetter is not None:
                    t = outputMinUseTimeGetter(outerO, t)

                assert len(o.obj.usedBy) == 1, ("Should be only bitwise operator with a single output", o)
                self.resolveSubnodeRealization(o.obj, len(o.obj._inputs))
                clkStartBoundary = indexOfClkPeriod(t, clkPeriod) * clkPeriod
                if t - o.obj.inputWireDelay[0] <= clkStartBoundary:
                    t = clkStartBoundary - ffdelay
                    clkStartBoundary -= clkPeriod

                o.obj._setScheduleZeroTimeSingleClock(t)

                # set time for all dependencies in this cluster as last as possible
                self.scheduleAlapCompactionForOutput(o,
                                                     clkStartBoundary,
                                                     SetList(),
                                                     outputMinUseTimeGetter,
                                                     excludeNode)

        self.copySchedulingFromChildren()
        for inT, dep in zip(self.scheduledIn, self.dependsOn):
            if inT < dep.obj.scheduledOut[dep.out_i]:
                # scheduling failed to meet timing requirements on at least one input
                # this node can not be moved and must stay as it was
                self.setScheduling(originalSchedule)
                return

        self.checkScheduling()

        if self.scheduledZero != scheduledZero or self.scheduledIn != scheduledIn or self.scheduledOut != scheduledOut:
            for dep in self.dependsOn:
                yield dep.obj
