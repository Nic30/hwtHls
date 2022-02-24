from math import inf
import math
from typing import List, Set, Dict, Optional

from hwt.hdl.operatorDefs import  AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.clk_math import start_of_next_clk_period, epsilon
from hwtHls.netlist.analysis.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.scheduler.errors import TimeConstraintError


class HlsNetlistNodeBitwiseOps(HlsNetNode):
    """
    Container of cluster of bitwise operators.

    :ivar _totalInputCnt: the dictionary mapping the nodes of cluster to a number of transitive inputs
        from outside of cluster.
    :ivar isFragmented: flag which is True if the node was split on parts and if parts should be used for allocation instead
        of this whole object.
    """

    def __init__(self, parentHls:"HlsPipeline", subNodes: HlsNetlistClusterSearch, name:str=None):
        HlsNetNode.__init__(self, parentHls, name=name)
        self._subNodes = subNodes
        for _ in subNodes.inputs:
            self._add_input()
        for o in subNodes.outputs:
            self._add_output(o._dtype)
        self._totalInputCnt: Dict[HlsNetNodeOperator, int] = {}
        self._isFragmented = False
        self.internOutToOut = {intern:outer for intern, outer in zip(self._subNodes.outputs, self._outputs)}
        self.outerOutToIn = {o:i for o, i in zip(self._subNodes.inputs, self._inputs)}

    def resolve_subnode_realization(self, node: HlsNetNodeOperator, input_cnt: int):
        hls = self.hls
        clk_period = hls.clk_period
        bit_length = node._outputs[0]._dtype.bit_length()

        if node.operator is AllOps.TERNARY:
            input_cnt = input_cnt // 2 + 1

        r = hls.platform.get_op_realization(
            node.operator, bit_length,
            input_cnt, clk_period)
        inp_latency = []
        assert len(node._inputs) >= len(node.dependsOn), (len(node._inputs), node.dependsOn)
        for dep in node.dependsOn:
            dep: HlsNetNodeOut
            if dep.obj in self._subNodes.nodes:
                t = max(dep.obj.latency_pre)
            else:
                t = 0.0
            inp_latency.append(t)
        latency_pre = r.latency_pre
        if not isinstance(latency_pre, float):
            latency_pre = latency_pre[0]
        r.latency_pre = tuple(
            max((lat - parent_lat, 0.0))
            for lat, parent_lat in zip(self._numberForEachInput(latency_pre), inp_latency)
        )
        node.assignRealization(r)

    def scheduleAsapWithQuantization(self, node: HlsNetNodeOperator, clk_period: float, pathForDebug: Optional[UniqList["HlsNetNode"]]):
        assert node in self._subNodes.nodes, (node, self._subNodes)
        if node._asapEnd is None:
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
                    _sch, _inp_cnt = self.scheduleAsapWithQuantization(obj, clk_period, pathForDebug)
                    totalInputCnt += _inp_cnt

                else:
                    _sch = obj.scheduleAsap(clk_period, pathForDebug)
                    totalInputCnt += 1
                   
                t = _sch[d.out_i]  # + epsilon
                input_times.append(t)

            self._totalInputCnt[node] = totalInputCnt
            self.resolve_subnode_realization(node, totalInputCnt)
            # now we have times when the value is available on input
            # and we must resolve the minimal time so each input timing constraints are satisfied
            time_when_all_inputs_present = 0.0
    
            for (available_in_time, in_delay, in_cycles) in zip(input_times, node.latency_pre, node.in_cycles_offset):
                if in_delay >= clk_period:
                    raise TimeConstraintError(
                        "Impossible scheduling, clk_period too low for ",
                        node.latency_pre, node.latency_post, node)
                
                next_clk_time = start_of_next_clk_period(available_in_time, clk_period)
                time_budget = next_clk_time - available_in_time
    
                if in_delay >= time_budget:
                    available_in_time = next_clk_time
    
                normalized_time = (available_in_time
                                   +in_delay
                                   +in_cycles * clk_period)
    
                if normalized_time > time_when_all_inputs_present:
                    time_when_all_inputs_present = normalized_time
    
            node.scheduledIn = node._asapBegin = tuple(
                time_when_all_inputs_present - (in_delay + in_cycles * clk_period) + epsilon
                for (in_delay, in_cycles) in zip(node.latency_pre, node.in_cycles_offset)
            )
    
            node.scheduledOut = node._asapEnd = tuple(
                time_when_all_inputs_present + out_delay + out_cycles * clk_period + epsilon
                for (out_delay, out_cycles) in zip(node.latency_post, node.cycles_latency)
            )
            for ot in node.scheduledOut:
                for it in node._asapBegin:
                    assert int(ot // clk_period) == int(it // clk_period), ("Bitwise operator primitives can not cross clock boundaries", node, it, ot, clk_period)

            if pathForDebug is not None:
                pathForDebug.pop()

        else:
            totalInputCnt = self._totalInputCnt[node]

        return node._asapEnd, totalInputCnt

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        ASAP scheduling with compaction
        """
        if self._asapEnd is None:
            if pathForDebug is not None:
                if self in pathForDebug:
                    raise AssertionError("Cycle in graph", self, [n._id for n in pathForDebug[pathForDebug.index(self):]])
                else:
                    pathForDebug.append(self)

            scheduleOut = []
            for o in self._subNodes.outputs:
                o: HlsNetNodeOut
                _scheduleOut, _ = self.scheduleAsapWithQuantization(o.obj, clk_period, pathForDebug)
                scheduleOut.append(_scheduleOut[0])
            
            self._asapBegin = tuple(min(use.obj._asapBegin[use.in_i] for use in self._subNodes.inputsDict[i]) for i in self._subNodes.inputs)
            self._asapEnd = tuple(scheduleOut)

        return self._asapEnd
    
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
                                       inputs: List[HlsNetNodeIn], outputs: List[HlsNetNodeOut]) -> Optional['HlsNetlistNodeBitwiseOpsPartRef']:
        """
        :see: :meth:`~.HlsNetNode.partsComplement`
        """
        assert inputs or outputs, self
        subNodes = HlsNetlistClusterSearch()
        parentNodeInPortMap = {outer: intern for  outer, intern in zip(self._inputs , self._subNodes.inputs)}
        parentNodeOutPortMap = {outer: intern for outer, intern in zip(self._outputs, self._subNodes.outputs)}
                   
        subNodes.inputs.extend(parentNodeInPortMap[i] for i in inputs)
        subNodes.outputs.extend(parentNodeOutPortMap[o] for o in outputs)

        n = HlsNetlistNodeBitwiseOpsPartRef(self.hls, self, subNodes, beginTime, endTime, name=self.name)
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

    def partsComplement(self, otherParts: List["HlsNetlistNodeBitwiseOpsPartRef"]):
        """
        :see: :meth:`~.HlsNetNode.partsComplement`
        """
        allNodes: Set[HlsNetNode] = set()
        allPartsIo: Set[HlsNetNodeOut] = set()
        for p in otherParts:
            p: HlsNetlistNodeBitwiseOpsPartRef
            assert p.parentNode is self, (self, p)
            allNodes.update(p._subNodes.nodes)
            allPartsIo.update(p._subNodes.inputs)
            allPartsIo.update(p._subNodes.outputs)
        
        c = HlsNetlistClusterSearch()
        c.nodes.extend(n for n in self._subNodes.nodes if n not in allNodes)
        
        beginTime = inf
        endTime = 0.0
        for n in c.nodes:
            n: HlsNetNode
            for iT, o in zip(n.scheduledIn, n.dependsOn):
                # external input or newly generated internal cluster input
                if o in self._subNodes.inputs or o in allPartsIo or o.obj not in c.nodes:
                    # input is any internal input if it is driven by something external
                    c.inputs.append(o)
                    beginTime = min(endTime, iT)

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
            yield HlsNetlistNodeBitwiseOpsPartRef(self.hls, self, c, beginTime, endTime)

    def __repr__(self, minify=False):
        if minify:
            return f"<{self.__class__.__name__:s} {self._id:d}>"
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {[n._id for n in self._subNodes.nodes]}>"


class HlsNetlistNodeBitwiseOpsPartRef(HlsNetNodePartRef, HlsNetlistNodeBitwiseOps):
    """
    The purpose of this object is to mark a subset of :class:`~.HlsNetlistNodeBitwiseOps` node for an allocator.
    This node does not create/have any own nodes or ports, instead it uses ports and nodes from original node sub nodes.
    This node thus can not be scheduled and relies on the scheduling from the parent node.
    """

    def __init__(self, parentHls:"HlsPipeline", parentNode:HlsNetNode, subNodes: HlsNetlistClusterSearch, beginTime:float, endTime:float, name:str=None):
        HlsNetlistNodeBitwiseOps.__init__(self, parentHls, subNodes, name=name)
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

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
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

    def iterScheduledClocks(self, clk_period: float):
        startClkI = int(self.beginTime // clk_period)
        endClkI = int(self.endTime // clk_period)
        yield from range(startClkI, startClkI + endClkI + 1)

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
