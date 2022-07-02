from math import inf
import math
from typing import List, Set, Dict, Optional

from hwt.hdl.operatorDefs import  AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.scheduler.clk_math import start_of_next_clk_period, start_clk
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef, SchedulizationDict, HlsNetNode_numberForEachInput
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
    """

    def __init__(self, netlist:"HlsNetlistCtx", subNodes: HlsNetlistClusterSearch, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._subNodes = subNodes
        for _ in subNodes.inputs:
            self._add_input()
        for o in subNodes.outputs:
            self._add_output(o._dtype)
        self._totalInputCnt: Dict[HlsNetNodeOperator, int] = {}
        self._isFragmented = False
        self.internOutToOut = {intern:outer for intern, outer in zip(self._subNodes.outputs, self._outputs)}
        self.outerOutToIn = {o:i for o, i in zip(self._subNodes.inputs, self._inputs)}

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

    def resetScheduling(self):
        for n in self._subNodes.nodes:
            n.resetScheduling()
        self.scheduledIn = None
        self.scheduledOut = None

    def scheduleAlapCompactionForOutput(self, internalOut: HlsNetNodeOut,
                                        asapSchedule: SchedulizationDict,
                                        clkBoundaryTime: int,
                                        currentInputs: UniqList[HlsNetNodeIn]):
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
                outT = self._getAlapOutsideOutTime(outerOut, asapSchedule)
            for pou in parentOutUses:
                pou: HlsNetNodeIn
                if pou.obj.scheduledIn is None:
                    outT = None
                    break

                else:
                    t = pou.obj.scheduledIn[pou.in_i]
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
                    parentOut.obj.scheduledOut = (clkBoundaryTime - ffdelay,)  # move to start of clock cycle - ffdealy
                    # all uses known and time corssing clock boundary, start a new cluster from this output
                    self.scheduleAlapCompactionForOutput(parentOut, asapSchedule, newClkStartBoundary - clkPeriod,
                                                         UniqList())
                else:
                    # somewhere inside clock cycle, no need to modify time
                    parentOut.obj.scheduledOut = (outT,)
                    self.scheduleAlapCompactionForOutput(parentOut, asapSchedule, clkBoundaryTime, currentInputs)

    def _getAlapOutsideOutTime(self, outerOut: HlsNetNodeOut, asapSchedule: SchedulizationDict):
        outsideClusterUses = outerOut.obj.usedBy[outerOut.out_i]
        assert outsideClusterUses, ("Must be connected to something because otherwise this should be removed because it is unused", outerOut)
        t = min(u.obj.scheduleAlapCompaction(asapSchedule)[u.in_i] for u in outsideClusterUses)
        return t

    def scheduleAlapCompaction(self, asapSchedule: SchedulizationDict):
        """
        1. Resolve ALAP times for all inputs outside of this node where outputs are connected.
           Note that this time is not the output time of internal output because output value may be required sooner.
           * The total delay of subgraph is specified by number of inputs.
           * The graph is cut on clock period boundaries.
           * The problem is that we know the latency once we know the number of inputs, but we need a latency in order
             to find out when the graph should be cut due to clock period poundary and from there we know the number of inputs.
           * Problem is that we do not know which output is most constraining.
        2. For each sub node perform ALAP compaction.
           Use external output times a starting points. For each output we have to count inputs from clock boundary
           so we can resolve the latency of the operator tree.
        3. Store in/out schedule of children to this parent node.
        """
        if self.scheduledIn is None:
            # :note: There must be at least a single output which is not used internally in the cluster
            #        because cluster node graph is cycle free
            for outerO, o in zip(self._outputs, self._subNodes.outputs):
                o: HlsNetNodeOut
                insideClusterUses = o.obj.usedBy[o.out_i]
                if not insideClusterUses:
                    netlist = self.netlist
                    # this is just output to outside, copy timing from outside input
                    outsideClusterUses = outerO.obj.usedBy[outerO.out_i]
                    assert outsideClusterUses, ("Must be connected to something because otherwise this should be removed because it is unused", outerO)
                    t = min(u.obj.scheduleAlapCompaction(asapSchedule)[u.in_i] for u in outsideClusterUses)
                    assert len(o.obj.usedBy) == 1, ("Should be only bitwise operator wit a single output", o)
                    self.resolveSubnodeRealization(o.obj, len(o.obj._inputs))
                    clkStartBoundary = start_clk(t, netlist.normalizedClkPeriod) * netlist.normalizedClkPeriod
                    if t - o.obj.inputWireDelay[0] <= clkStartBoundary:
                        ffdelay = netlist.platform.get_ff_store_time(self.netlist.realTimeClkPeriod, self.netlist.scheduler.resolution)
                        t = clkStartBoundary - ffdelay
                        clkStartBoundary -= netlist.normalizedClkPeriod
                    o.obj.scheduledOut = (t,)
                    self.scheduleAlapCompactionForOutput(o,
                                                         asapSchedule,
                                                         clkStartBoundary,
                                                         UniqList())

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

    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement"):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """
        if self._isFragmented:
            # Parts should be used for allocation instead of this node.
            for part in allocator.interArchAnalysis.partsOfNode[self]:
                if part in allocator.allNodes:
                    part.allocateRtlInstance(allocator)
        else:
            assert len(self._outputs) == len(self._subNodes.outputs)
            for outerO, o in zip(self._outputs, self._subNodes.outputs):
                outerO: HlsNetNodeOut
                o: HlsNetNodeOut
                assert outerO.obj is self
                if outerO in allocator.netNodeToRtl:
                    continue

                o = allocator.instantiateHlsNetNodeOut(o)
                allocator.netNodeToRtl[outerO] = o

    def createSubNodeRefrenceFromPorts(self, beginTime: float, endTime: float,
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> Optional['HlsNetNodeBitwiseOpsPartRef']:
        """
        :see: :meth:`~.HlsNetNode.partsComplement`
        """
        assert inputs or outputs, self
        subNodes = HlsNetlistClusterSearch()
        parentNodeInPortMap = {outer: intern for  outer, intern in zip(self._inputs , self._subNodes.inputs)}
        parentNodeOutPortMap = {outer: intern for outer, intern in zip(self._outputs, self._subNodes.outputs)}

        subNodes.inputs.extend(parentNodeInPortMap[i] for i in inputs)
        subNodes.outputs.extend(parentNodeOutPortMap[o] for o in outputs)

        n = HlsNetNodeBitwiseOpsPartRef(self.netlist, self, subNodes, beginTime, endTime, name=self.name)
        for i in subNodes.inputs:
            # for nodes internally in the subNodes, transitively discover
            # things connected to this input until the boundary is meet
            atLeastOnceUsed = False
            usesInCluster = self._subNodes.inputsDict[i]
            for use in usesInCluster:
                if use.obj.scheduledIn[use.in_i] <= endTime:
                    n._discoverFromIn(use.obj)
                    atLeastOnceUsed = True
            assert atLeastOnceUsed, (i, "Must be at least once used because if it was used only later it should be also scheduled only later")

        for o in subNodes.outputs:
            n._discoverFromOut(o)

        for node in subNodes.nodes:
            for o, uses in zip(node._outputs, node.usedBy):
                if o in self._subNodes.outputs or any(u.obj not in subNodes.nodes for u in uses):
                    subNodes.outputs.append(o)

            for dep in node.dependsOn:
                if dep.obj not in subNodes.nodes:
                    subNodes.inputs.append(dep)

        assert subNodes.nodes
        # all inputs of some used node but not connected to any used node are treated ans new inputs
        assert subNodes.inputs, (beginTime, endTime, self, [n._id for n in subNodes.nodes])
        assert subNodes.outputs, (beginTime, endTime, self, [n._id for n in subNodes.nodes])
        allNodes = self._subNodes.nodes
        for sn in subNodes.nodes:
            assert sn in allNodes
        self._isFragmented = True
        for i in subNodes.inputs:
            assert i.obj not in subNodes.nodes, ("Should not be an input if the node in this cluster", i)
        return n

    def partsComplement(self, otherParts: List["HlsNetNodeBitwiseOpsPartRef"]):
        """
        :see: :meth:`~.HlsNetNode.partsComplement`
        """
        allNodes: Set[HlsNetNode] = set()
        allPartsIo: Set[HlsNetNodeOut] = set()
        for p in otherParts:
            p: HlsNetNodeBitwiseOpsPartRef
            assert p.parentNode is self, (self, p)
            allNodes.update(p._subNodes.nodes)
            allPartsIo.update(p._subNodes.inputs)
            allPartsIo.update(p._subNodes.outputs)

        c = HlsNetlistClusterSearch()
        c.nodes.extend(n for n in self._subNodes.nodes if n not in allNodes)

        beginTime = inf
        endTime = 0
        for n in c.nodes:
            n: HlsNetNode
            for iT, o in zip(n.scheduledIn, n.dependsOn):
                # external input or newly generated internal cluster input
                if o in self._subNodes.inputs or o in allPartsIo or o.obj not in c.nodes:
                    # input is any internal input if it is driven by something external
                    c.inputs.append(o)
                    beginTime = min(beginTime, iT)

            for o, oT, uses in zip(n._outputs, n.scheduledOut, n.usedBy):
                # :note: works only for subnodes which can fit in single clock period
                if o in self._subNodes.outputs or o in allPartsIo or any(u.obj not in c.nodes for u in uses):
                    # output is any internal output if the output is used by something external
                    c.outputs.append(o)
                    endTime = max(endTime, oT)
            # newly generated internal cluster outputs

        if c.nodes:
            # [todo] split independet subgraphs
            assert c.inputs
            assert c.outputs
            yield HlsNetNodeBitwiseOpsPartRef(self.netlist, self, c, beginTime, endTime)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {[n._id for n in self._subNodes.nodes]}>"


class HlsNetNodeBitwiseOpsPartRef(HlsNetNodePartRef, HlsNetNodeBitwiseOps):
    """
    The purpose of this object is to mark a subset of :class:`~.HlsNetNodeBitwiseOps` node for an allocator.
    This node does not create/have any own nodes or ports, instead it uses ports and nodes from original node sub nodes.
    This node thus can not be scheduled and relies on the scheduling from the parent node.
    """

    def __init__(self, netlist:"HlsNetlistCtx", parentNode:HlsNetNode, subNodes: HlsNetlistClusterSearch, beginTime:float, endTime:float, name:str=None):
        HlsNetNodeBitwiseOps.__init__(self, netlist, subNodes, name=name)
        # not using this as this is just reference and real value is stored in parent
        self._inputs = None
        self._outputs = None
        self.dependsOn = None
        self.usedBy = None
        self.scheduledIn = None
        self.scheduledOut = None

        self.parentNode = parentNode
        self.beginTime = beginTime
        self.endTime = endTime
 
    def moveSchedulingTime(self, offset:int):
        raise AssertionError("This node should not be scheduled because parent node should be scheduled instead")

    def scheduleAsap(self, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        ASAP scheduling with compaction
        """
        raise AssertionError("This node should not be scheduled because parent node should be scheduled instead")

    def _discoverFromIn(self, obj: HlsNetNode):
        """
        DFS in->out until time is meet or external node found
        """
        assert obj is not self.parentNode, obj
        self._subNodes.nodes.append(obj)
        for t, dep in zip(obj.scheduledIn, obj.dependsOn):
            t: float
            dep: HlsNetNodeOut

            if t < self.beginTime:
                raise NotImplementedError("Need to split also node", obj, "inside of aggregated node", self, "because it is crossing time boundary")

            if dep.obj.scheduledOut[dep.out_i] < self.beginTime:
                # this input is connected to something external
                # :note: this should not be the case because we already should have all inputs and we are
                # going in the direction ->
                continue

        for ot, o, uses  in zip(obj.scheduledOut, obj._outputs, obj.usedBy):
            if ot <= self.endTime:
                usedByExtern = False
                for it2, i2 in zip(o.obj.scheduledIn, uses):
                    if i2.obj in self._subNodes.nodes and it2 < self.endTime:
                        self._discoverFromIn(i2.obj)
                    else:
                        usedByExtern = True

                if usedByExtern:
                    self._subNodes.outputs.append(o)

    def _discoverFromOut(self, out_: HlsNetNodeOut):
        """
        DFS out->in until time is meet or external node found
        """
        if out_.obj is self.parentNode:
            # if this a case we need to use output from subNodes
            out_ = self.parentNode._subNodes.outputs[out_.out_i]

        assert out_.obj is not self.parentNode
        self._subNodes.nodes.append(out_.obj)

        beginTime = self.beginTime
        for t, dep in zip(out_.obj.scheduledIn, out_.obj.dependsOn):
            t: float
            dep: HlsNetNodeOut

            if t < beginTime:
                raise NotImplementedError("Need to split also this subnode", out_.obj, "inside of aggregated node", self, "because it is crossing time boundary", (t, self.beginTime))

            ot = dep.obj.scheduledOut[dep.out_i]
            if ot < beginTime or math.isclose(ot, beginTime, rel_tol=1e-09) or out_ in self._subNodes.outputs:
                # this input is connected to something external
                pass
                # self._subNodes.inputs.append(out_)
            else:
                # this input is connected to output which is also part of this node part, continue search
                self._discoverFromOut(dep.obj)

    def iterScheduledClocks(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        startClkI = int(self.beginTime // clkPeriod)
        endClkI = int(self.endTime // clkPeriod)
        yield from range(startClkI, endClkI + 1)

    def allocateRtlInstance(self, allocator:"AllocatorArchitecturalElement"):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """

        assert self._subNodes.outputs, self
        for o in self._subNodes.outputs:
            o: HlsNetNodeOut

            outerO = self.parentNode.internOutToOut.get(o, None)
            if o not in allocator.netNodeToRtl:
                oRtl = allocator.instantiateHlsNetNodeOut(o)
                if outerO is not None and outerO not in allocator.netNodeToRtl:
                    allocator.netNodeToRtl[outerO] = oRtl
            elif outerO is not None and outerO not in allocator.netNodeToRtl:
                oRtl = allocator.netNodeToRtl[o]
                allocator.netNodeToRtl[outerO] = oRtl

    def __repr__(self, minify=False):
        return f"<{self.__class__.__name__:s} {self._id:d} for {self.parentNode._id:d} {[n._id for n in self._subNodes.nodes]}>"
