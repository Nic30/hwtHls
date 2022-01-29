from typing import List, Set, Dict, Optional

from hwt.hdl.operatorDefs import BITWISE_OPS, AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.allocator.connectionsOfStage import SignalsOfStages
from hwtHls.clk_math import start_of_next_clk_period, epsilon
from hwtHls.netlist.analysis.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.scheduler.errors import TimeConstraintError
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource


class HlsNetlistNodeBitwiseOps(HlsNetNode):
    """
    Container of cluster of bitwise operators.
    :ivar _totalInputCnt: the dictionary mapping the nodes of cluster to a number of transitive inputs
        from outside of cluster.
    """

    def __init__(self, parentHls:"HlsPipeline", subNodes: HlsNetlistClusterSearch, name:str=None):
        HlsNetNode.__init__(self, parentHls, name=name)
        self._subNodes = subNodes
        for _ in subNodes.inputs:
            self._add_input()
        for o in subNodes.outputs:
            self._add_output(o._dtype)
        self._totalInputCnt: Dict[HlsNetNodeOperator, int] = {}
        self._forwardRtlDeclaredOutputs: Set[HlsNetNodeOut] = set()

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
        if node.asap_end is None:
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
                   
                t = _sch[d.out_i]
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
    
                if normalized_time >= time_when_all_inputs_present:
                    # latest_input_i = in_i
                    time_when_all_inputs_present = normalized_time
    
            node.scheduledIn = node.asap_start = tuple(
                time_when_all_inputs_present - (in_delay + in_cycles * clk_period)
                for (in_delay, in_cycles) in zip(node.latency_pre, node.in_cycles_offset)
            )
    
            node.scheduledOut = node.asap_end = tuple(
                time_when_all_inputs_present + out_delay + out_cycles * clk_period
                for (out_delay, out_cycles) in zip(node.latency_post, node.cycles_latency)
            )
            if pathForDebug is not None:
                pathForDebug.pop()

        else:
            totalInputCnt = self._totalInputCnt[node]

        return node.asap_end, totalInputCnt

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["HlsNetNode"]]) -> List[float]:
        """
        ASAP scheduling with compaction
        """
        if self.asap_end is None:
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
            
            self.asap_start = tuple(dep.obj.asap_end[dep.out_i] for dep in self.dependsOn)
            self.asap_end = tuple(scheduleOut)
        return self.asap_end
    
    def replaceAllOuterInputsPlaceholders(self, outputMap: Optional[Dict[HlsNetNodeOut, HlsNetNodeOut]]):
        for n in self._subNodes.nodes:
            for i, dep in enumerate(n.dependsOn):
                if isinstance(dep, HlsNetNodeIn):
                    assert dep.obj is self, (self, dep.obj, n._id)
                    o = self.dependsOn[dep.in_i]
                    if outputMap:
                        o = outputMap.get(o, o)
                    n.dependsOn[i] = o

    def allocateRtlInstanceOutDeclr(self, allocator: "HlsAllocator", o: HlsNetNodeOut):
        assert allocator.netNodeToRtl.get(o, None) is None, ("Must not be redeclared", o)
        s = allocator._sig(f"forwardDeclr{self.name}_{o.out_i:d}", o._dtype)
        allocator.netNodeToRtl[o] = TimeIndependentRtlResource(s, self.scheduledOut[o.out_i] + epsilon, allocator)
        self._forwardRtlDeclaredOutputs.add(o)
                
    def allocateRtlInstance(self,
            allocator:"HlsAllocator",
            used_signals: SignalsOfStages):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """
        for outerO, o, t in zip(self._outputs, self._subNodes.outputs, self.scheduledOut):
            outerO: HlsNetNodeOut
            o: HlsNetNodeOut
            if outerO in self._forwardRtlDeclaredOutputs:
                raise NotImplementedError()

            if outerO in allocator.netNodeToRtl:
                # this node was already allocated
                return

            o = allocator.instantiateHlsNetNodeOut(o, used_signals)
            allocator._registerSignal(outerO, o, used_signals.getForTime(t))

    def __repr__(self, minify=False):
        return f"<{self.__class__.__name__:s} {self._id:d} {[n._id for n in self._subNodes.nodes]}>"


class HlsNetlistPassAggregateBitwiseOps(HlsNetlistPass):
    """
    Extract cluster of bitwise operators as a single node to simplify scheduling.
    """

    def _isBitwiseOperator(self, n: HlsNetNode):
        return isinstance(n, HlsNetNodeOperator) and n.operator in BITWISE_OPS
        
    def apply(self, hls: "HlsStreamProc", to_hw: "SsaSegmentToHwPipeline"):
        seen: Set[HlsNetNodeOperator] = set()
        removedNodes: Set[HlsNetNode] = set()
        newOutMap: Dict[HlsNetNodeOut, HlsNetNodeOut] = {}
        # discovert clusters of bitwise operators
        for n in to_hw.hls.nodes:
            if n not in seen and self._isBitwiseOperator(n):
                    cluster = HlsNetlistClusterSearch()
                    cluster.discover(n, seen, self._isBitwiseOperator)
                    if len(cluster.nodes) > 1:
                        for c in cluster.splitToPreventOuterCycles():
                            if len(c.nodes) > 1:
                                c.updateOuterInputs(newOutMap)
                                clusterNode = HlsNetlistNodeBitwiseOps(to_hw.hls, c)
                                to_hw.hls.nodes.append(clusterNode)
                                c.substituteWithNode(clusterNode)
                                removedNodes.update(c.nodes)
                                for o, internO in zip(clusterNode._outputs, c.outputs):
                                    newOutMap[internO] = o
                                clusterNode.replaceAllOuterInputsPlaceholders(newOutMap)

        to_hw.hls.nodes = [n for n in to_hw.hls.nodes if n not in removedNodes]
