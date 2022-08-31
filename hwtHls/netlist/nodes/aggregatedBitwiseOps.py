from typing import List, Dict, Optional

from hwt.hdl.operatorDefs import  AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, start_clk
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.nodes.node import HlsNetNode, SchedulizationDict, InputTimeGetter, HlsNetNode_numberForEachInput
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.scheduler.errors import TimeConstraintError


class HlsNetNodeBitwiseOps(HlsNetNode):
    """
    Container of cluster of bitwise operators.

    :ivar _totalInputCnt: the dictionary mapping the nodes of cluster to a number of transitive inputs
        from outside of cluster.
    :ivar isFragmented: flag which is True if the node was split on parts and if parts should be used for allocation instead
        of this whole object.
    :ivar internOutToOut: a dictionary mapping output of internal node to an output of this node
    :ivar outerOutToIn: a dictionary mapping a 
    """

    def __init__(self, netlist:"HlsNetlistCtx", subNodes: HlsNetlistClusterSearch, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._subNodes = subNodes
        for _ in subNodes.inputs:
            self._addInput(None)
        for o in subNodes.outputs:
            self._addOutput(o._dtype, None)
        self._totalInputCnt: Dict[HlsNetNodeOperator, int] = {}
        self._isFragmented = False
        self.internOutToOut: Dict[HlsNetNodeOut, HlsNetNodeOut] = {
            intern:outer for intern, outer in zip(self._subNodes.outputs, self._outputs)
        }
        self.outerOutToIn: Dict[HlsNetNodeOut, HlsNetNodeIn] = {
            o:i for o, i in zip(self._subNodes.inputs, self._inputs)
        }

    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        HlsNetNode.destroy(self)
        self._subNodes.destroy()
        self._subNodes = None
        self._totalInputCnt = None
        self.internOutToOut = None
        self.outerOutToIn = None
        
    def copyScheduling(self, schedule: SchedulizationDict):
        for n in self._subNodes.nodes:
            n.copyScheduling(schedule)
        schedule[self] = (self.scheduledIn, self.scheduledOut)
    
    def moveSchedulingTime(self, offset:int):
        HlsNetNode.moveSchedulingTime(self, offset)
        for n in self._subNodes.nodes:
            n.moveSchedulingTime(offset)

    def checkScheduling(self):
        HlsNetNode.checkScheduling(self)
        for n in self._subNodes.nodes:
            n.checkScheduling()

        # assert that io of this node has correct times
        for outer, intern in zip(self._inputs , self._subNodes.inputs):
            pass
        for outer, intern in zip(self._outputs, self._subNodes.outputs):
            assert outer.obj is self
            assert intern.obj in self._subNodes.nodes
            assert self.scheduledOut[outer.out_i] == intern.obj.scheduledOut[intern.out_i]

    def resetScheduling(self):
        for n in self._subNodes.nodes:
            n.resetScheduling()
        self.scheduledIn = None
        self.scheduledOut = None

    def scheduleAlapCompactionForOutput(self, internalOut: HlsNetNodeOut,
                                        asapSchedule: SchedulizationDict,
                                        clkBoundaryTime: int,
                                        currentInputs: UniqList[HlsNetNodeIn],
                                        inputTimeGetter: Optional[InputTimeGetter]):
        """
        BFS consume all inputs until the start or until the boundary is found
        
        :ivar internalOut: Internal output with known scheduling time. (Time is known if all uses of this output have known time)
        """
        # candidateOutputs = deque()
        # 1. set input time for every input
        # inputCntWithoutThisNode = min(1, len(currentInputs))
        currentInputs.extend(internalOut.obj._inputs)
        timeOffset = internalOut.obj.scheduledOut[internalOut.out_i]
        internalOut.obj.scheduledIn = tuple(timeOffset - lat for lat in internalOut.obj.inputWireDelay)
        ffdelay = self.netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
        clkPeriod = self.netlist.normalizedClkPeriod
        # 2. resolve which nodes we can add to cluster because they have all successors known
        #    and adding it will not cause time to overflow clkBoundaryTime
        for parentOut in internalOut.obj.dependsOn:
            if parentOut in self._subNodes.inputs:
                continue  # skip ALAP for external inputs, we will continue there once we resolve all nodes in this cluster
            parentOutUses = parentOut.obj.usedBy[parentOut.out_i]
            outT = None
            outerOut = self.internOutToOut.get(parentOut, None)
            if outerOut is not None:
                outT = self._getAlapOutsideOutTime(outerOut, asapSchedule, inputTimeGetter)
            for pou in parentOutUses:
                pou: HlsNetNodeIn
                if pou.obj.scheduledIn is None:
                    outT = None
                    break

                else:
                    if inputTimeGetter is None:
                        t = pou.obj.scheduledIn[pou.in_i]
                    else:
                        t = inputTimeGetter(pou, asapSchedule)

                    if outT is None:
                        outT = t
                    else:
                        outT = min(outT, t)

            if outT is not None:
                assert parentOut.obj.scheduledOut is None or parentOut.obj.scheduledOut[0] == outT, (
                    "The node was not supposed to be scheduled because we should not see this use of this output yet",
                    parentOut, outT, parentOut.obj.scheduledOut[0])
                assert len(parentOut.obj._outputs) == 1, (parentOut.obj._outputs, "Only operators with a single output expected")
                self.resolveSubnodeRealization(parentOut.obj, len(currentInputs) + len(parentOut.obj._inputs))
                if outT - parentOut.obj.inputWireDelay[0] <= clkBoundaryTime:
                    newClkStartBoundary = start_clk(outT, clkPeriod) * clkPeriod
                    # can not fit this node inside current clock cycle
                    parentOut.obj.scheduledOut = (min(clkBoundaryTime - ffdelay, outT),)  # move to start of clock cycle - ffdealy
                    # all uses known and time corssing clock boundary, start a new cluster from this output
                    self.scheduleAlapCompactionForOutput(parentOut, asapSchedule, newClkStartBoundary - clkPeriod,
                                                         UniqList(), inputTimeGetter)
                else:
                    # somewhere inside clock cycle, no need to modify time
                    parentOut.obj.scheduledOut = (outT,)
                    self.scheduleAlapCompactionForOutput(parentOut, asapSchedule, clkBoundaryTime, currentInputs, inputTimeGetter)

    def _getAlapOutsideOutTime(self, outerOut: HlsNetNodeOut, asapSchedule: SchedulizationDict, inputTimeGetter: Optional[InputTimeGetter]):
        outsideClusterUses = outerOut.obj.usedBy[outerOut.out_i]
        assert outsideClusterUses, ("Must be connected to something because otherwise this should be removed because it is unused", outerOut)
        if inputTimeGetter is None:
            t = min(u.obj.scheduleAlapCompaction(asapSchedule, None)[u.in_i] for u in outsideClusterUses)
        else:
            t = min(inputTimeGetter(u, asapSchedule) for u in outsideClusterUses)
        
        return t

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict, inputTimeGetter: Optional[InputTimeGetter]):
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
        if self.scheduledIn is None:
            # :note: There must be at least a single output which is not used internally in the cluster
            #        because cluster node graph is cycle free
            netlist = self.netlist
            clkPeriod = netlist.normalizedClkPeriod
            ffdelay = netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
            for outerO, o in zip(self._outputs, self._subNodes.outputs):
                o: HlsNetNodeOut
                insideClusterUses = o.obj.usedBy[o.out_i]
                if not insideClusterUses:
                    # this is just output to outside, copy timing from outside input
                    outsideClusterUses = outerO.obj.usedBy[outerO.out_i]
                    assert outsideClusterUses, ("Must be connected to something because otherwise this should be removed because it is unused", outerO)
                    if inputTimeGetter is None:
                        t = min(u.obj.scheduleAlapCompaction(asapSchedule, None)[u.in_i] for u in outsideClusterUses)
                    else:
                        t = min(inputTimeGetter(u, asapSchedule) for u in outsideClusterUses)
                        
                    assert len(o.obj.usedBy) == 1, ("Should be only bitwise operator wit a single output", o)
                    self.resolveSubnodeRealization(o.obj, len(o.obj._inputs))
                    clkStartBoundary = start_clk(t, clkPeriod) * clkPeriod
                    if t - o.obj.inputWireDelay[0] <= clkStartBoundary:
                        t = clkStartBoundary - ffdelay
                        clkStartBoundary -= clkPeriod

                    o.obj.scheduledOut = (t,)
                    self.scheduleAlapCompactionForOutput(o,
                                                         asapSchedule,
                                                         clkStartBoundary,
                                                         UniqList(),
                                                         inputTimeGetter)

            self.scheduledIn = tuple(min(
                                            use.obj.scheduledIn[use.in_i]
                                            for use in self._subNodes.inputsDict[i])
                                         for i in self._subNodes.inputs)
            self.scheduledOut = tuple(o.obj.scheduledOut[o.out_i] for o in self._subNodes.outputs)

        return self.scheduledIn

    def resolveSubnodeRealization(self, node: HlsNetNodeOperator, input_cnt: int):
        netlist = self.netlist
        bit_length = node._outputs[0]._dtype.bit_length()

        if node.operator is AllOps.TERNARY:
            input_cnt = input_cnt // 2 + 1

        rWithThisNode = netlist.platform.get_op_realization(
            node.operator, bit_length,
            input_cnt, netlist.realTimeClkPeriod)

        if input_cnt == 1 and node.operator == AllOps.NOT or input_cnt == 2:
            node.assignRealization(rWithThisNode)  # the first operator in cluster does not need any latency modifications
            return

        rWithoutThisNode = netlist.platform.get_op_realization(
            node.operator, bit_length,
            input_cnt - 2, netlist.realTimeClkPeriod)

        # substract the latency which is counted in some input latency
        if not isinstance(rWithThisNode.inputClkTickOffset, int):
            rWithThisNode.inputClkTickOffset = rWithoutThisNode.inputClkTickOffset[:2]

        inputWireDelay_with = rWithThisNode.inputWireDelay
        if not isinstance(inputWireDelay_with, (int, float)):
            inputWireDelay_with = inputWireDelay_with[:2]

        inputWireDelay_without = rWithoutThisNode.inputWireDelay
        if not isinstance(inputWireDelay_without, (int, float)):
            inputWireDelay_without = inputWireDelay_without[:2]

        rWithThisNode.inputWireDelay = tuple(
            max((latWith - latWithout, 0))
            for latWith, latWithout in zip(HlsNetNode_numberForEachInput(node, inputWireDelay_without),
                                           HlsNetNode_numberForEachInput(node, inputWireDelay_without))
        )
        node.assignRealization(rWithThisNode)

    def scheduleAsapWithQuantization(self, node: HlsNetNodeOperator, pathForDebug: Optional[UniqList["HlsNetNode"]]):
        assert node in self._subNodes.nodes, (node, self._subNodes)
        if node.scheduledOut is None:
            if pathForDebug is not None:
                if node in pathForDebug:
                    raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(node):]])
                else:
                    pathForDebug.append(self)

            totalInputCnt = 0
            input_times = []
            for d in node.dependsOn:
                obj = d.obj
                if obj in self._subNodes.nodes:
                    _sch, _inp_cnt = self.scheduleAsapWithQuantization(obj, pathForDebug)
                    totalInputCnt += _inp_cnt

                else:
                    _sch = obj.scheduleAsap(pathForDebug)
                    totalInputCnt += 1

                t = _sch[d.out_i]  # + epsilon
                input_times.append(t)

            self._totalInputCnt[node] = totalInputCnt
            self.resolveSubnodeRealization(node, totalInputCnt)
            # now we have times when the value is available on input
            # and we must resolve the minimal time so each input timing constraints are satisfied
            time_when_all_inputs_present = 0

            clkPeriod = self.netlist.normalizedClkPeriod
            epsilon = self.netlist.scheduler.epsilon
            for (available_in_time, in_delay, in_cycles) in zip(input_times, node.inputWireDelay, node.inputClkTickOffset):
                if in_delay >= clkPeriod:
                    raise TimeConstraintError(
                        "Impossible scheduling, clkPeriod too low for ",
                        node.inputWireDelay, node.outputWireDelay, node)

                next_clk_time = start_of_next_clk_period(available_in_time, clkPeriod)
                time_budget = next_clk_time - available_in_time

                if in_delay >= time_budget:
                    available_in_time = next_clk_time

                normalized_time = (available_in_time
                                   +in_delay
                                   +in_cycles * clkPeriod)

                if normalized_time > time_when_all_inputs_present:
                    time_when_all_inputs_present = normalized_time

            node.scheduledIn = tuple(
                time_when_all_inputs_present - (in_delay + in_cycles * clkPeriod) + epsilon
                for (in_delay, in_cycles) in zip(node.inputWireDelay, node.inputClkTickOffset)
            )

            node.scheduledOut = tuple(
                time_when_all_inputs_present + out_delay + out_cycles * clkPeriod + epsilon
                for (out_delay, out_cycles) in zip(node.outputWireDelay, node.outputClkTickOffset)
            )
            for ot in node.scheduledOut:
                for it in node.scheduledIn:
                    assert int(ot // clkPeriod) == int(it // clkPeriod), ("Bitwise operator primitives can not cross clock boundaries", node, it, ot, clkPeriod)

            if pathForDebug is not None:
                pathForDebug.pop()

        else:
            totalInputCnt = self._totalInputCnt[node]

        return node.scheduledOut, totalInputCnt

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        ASAP scheduling with compaction
        """
        if self.scheduledOut is None:
            if pathForDebug is not None:
                if self in pathForDebug:
                    raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                else:
                    pathForDebug.append(self)

            scheduleOut = []
            for o in self._subNodes.outputs:
                o: HlsNetNodeOut
                _scheduleOut, _ = self.scheduleAsapWithQuantization(o.obj, pathForDebug)
                scheduleOut.append(_scheduleOut[0])

            self.scheduledIn = tuple(min(use.obj.scheduledIn[use.in_i] for use in self._subNodes.inputsDict[i]) for i in self._subNodes.inputs)
            self.scheduledOut = tuple(scheduleOut)

        return self.scheduledOut

    def _replaceAllOuterInputsPlaceholders(self, outputMap: Optional[Dict[HlsNetNodeOut, HlsNetNodeOut]]):
        for n in self._subNodes.nodes:
            for i, dep in enumerate(n.dependsOn):
                if isinstance(dep, HlsNetNodeIn):
                    assert dep.obj is self, (self, dep.obj, n._id)
                    o = self.dependsOn[dep.in_i]
                    if outputMap:
                        o = outputMap.get(o, o)
                    n.dependsOn[i] = o

    def allocateRtlInstance(self, allocator:"ArchElement"):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """
        raise AssertionError("This node should be dissolved before instantiation to avoid complicated cases where parts are scattered over many arch elements.")

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {[n._id for n in self._subNodes.nodes]}>"

