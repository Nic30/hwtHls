from typing import List, Set, Dict, Callable, Optional

from hwt.hdl.operatorDefs import BITWISE_OPS, AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.allocator.connectionsOfStage import SignalsOfStages
from hwtHls.clk_math import start_of_next_clk_period
from hwtHls.netlist.nodes.ops import AbstractHlsOp, HlsOperation
from hwtHls.netlist.nodes.ports import HlsOperationIn, HlsOperationOut, \
    link_hls_nodes
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.scheduler.errors import TimeConstraintError


class HlsNetlistClusterSearch():
    """
    This class implements bidirectional floding of the net while predicate is satisfied.
    Collects nodes and inputs/outputs, has methods for manipulation with selection.
    """

    def __init__(self):
        # output ports of outside nodes
        self.inputs: List[HlsOperationOut] = []
        self.inputsDict: Dict[HlsOperationOut, UniqList[HlsOperationIn]] = {}
        # output ports of inside nodes
        self.outputs: UniqList[HlsOperationOut] = UniqList()
        self.nodes: UniqList[AbstractHlsOp] = UniqList()
        
    def _discover(self, n: AbstractHlsOp, seen: Set[AbstractHlsOp],
                 predicateFn: Callable[[AbstractHlsOp], bool]):
        """
        :attention: the inuts and outputs may by falsely detected if there are connections
            which are crossing the layers of the circuit (which usually the case)
        """
        self.nodes.append(n)
        seen.add(n)
        for inp, dep in zip(n._inputs, n.dependsOn):
            dep: HlsOperationOut
            depObj = dep.obj
            if depObj not in seen and predicateFn(depObj):
                self._discover(depObj, seen, predicateFn)
            else:
                o = depObj._outputs[dep.out_i]
                otherConnectedInputs = self.inputsDict.get(o, None)
                if otherConnectedInputs is None:
                    otherConnectedInputs = set()
                    self.inputsDict[o] = otherConnectedInputs
                    self.inputs.append(dep)
                otherConnectedInputs.add(inp)
        
        for outp, users in zip(n._outputs, n.usedBy):
            for u in users:
                u: HlsOperationIn
                uObj = u.obj
                if uObj not in seen and predicateFn(uObj):
                    self._discover(uObj, seen, predicateFn)            
                else:
                    if outp not in self.outputs:
                        self.outputs.append(outp)

    def discover(self, n: AbstractHlsOp, seen: Set[AbstractHlsOp],
                 predicateFn: Callable[[AbstractHlsOp], bool]):
        """
        Discover the cluster from the node n.
        """
        self._discover(n, seen, predicateFn)
        self.inputs = [i for i in self.inputs if i.obj not in self.nodes]
        # self.outputs = [o for o in self.outputs if o.obj not in self.nodes]
    
    def substituteWithNode(self, n: AbstractHlsOp):
        """
        Substitute all nodes with the cluster with a single node. All nodes are removed from netlists and disconnected on outer side.
        On inner side the information about connection is kept.
        """
        assert len(self.inputs) == len(n._inputs)
        assert len(self.outputs) == len(n._outputs)
        for boundaryIn, outerOutput in zip(n._inputs, self.inputs):
            outerOutput: HlsOperationOut
            interInputs = self.inputsDict[outerOutput]
            usedBy = outerOutput.obj.usedBy[outerOutput.out_i]
            usedBy = outerOutput.obj.usedBy[outerOutput.out_i] = [
                i
                for i in usedBy
                if i not in interInputs
            ]
            link_hls_nodes(outerOutput, boundaryIn)
            # :note: the inputs still have the record in dependsOn which tells them that
            # they are still connected to output
            # howere all nodes in cluster should be removed from the netlist and we keep this information
            # about where the removed nodes were connected
        
        clusterNodes = self.nodes
        for boundaryOut, interOutput in zip(n._outputs, self.outputs):
            # disconnect interOutput from all external inputs
            # and connect them to bounary output of node
            usedBy = interOutput.obj.usedBy[interOutput.out_i]
            for in_ in usedBy:
                if in_.obj not in clusterNodes:
                    in_.obj.dependsOn[in_.in_i] = boundaryOut
            interOutput.obj.usedBy[interOutput.out_i] = [in_ for in_ in usedBy if in_.obj in clusterNodes]
    
    def doesOutputLeadsToInputOfCluster(self, node: AbstractHlsOp,
                                        seenNodes: Set[HlsOperationOut]) -> bool:
        """
        Transitively check if the node outputs leads to some input of this cluster.
        """
        seenNodes.add(node)
        # print(node)
        for o, usedBy in zip(node._outputs, node.usedBy):
            o: HlsOperationOut
            for u in usedBy:
                u: HlsOperationIn
                if u.obj in self.nodes:
                    # this output leads back to some input of this cluster
                    if node not in self.nodes:
                        # only if this is an outer cycle
                        return True

                    seenNodes.add(o.obj)
                else:
                    if u.obj not in seenNodes:
                        if self.doesOutputLeadsToInputOfCluster(u.obj, seenNodes):
                            return True
        return False

    def collectPredecesorsInCluster(self, node: AbstractHlsOp):
        """
        Transitively collect all nodes which drive inputs of this node until cluster boundary is meet.
        """
        yield node
        for dep in node.dependsOn:
            if dep.obj in self.nodes:
                yield from self.collectPredecesorsInCluster(dep.obj)
   
    def splitToPreventOuterCycles(self):
        """
        If the cluster construction resulted into an outer cycle cut this cluster so the cycle dissapears.
        """
        # >1 because if tere was just 1 output the cycle has been there even before this cluster was generated. 
        if len(self.outputs) > 1:
            outputsCausingLoop: List[HlsOperationOut] = []
            for o in self.outputs:
                seenNodes: Set[AbstractHlsOp] = set()
                if self.doesOutputLeadsToInputOfCluster(o.obj, seenNodes):
                    outputsCausingLoop.append(o)

            if outputsCausingLoop:
                # cut of nodes with problematic nodes and all their predecessors to separate cluster
                predCluster = HlsNetlistClusterSearch()
                for o in outputsCausingLoop:
                    predCluster.nodes.extend(self.collectPredecesorsInCluster(o.obj))

                newInputs = []
                for i in self.inputs:
                    added0 = False
                    added1 = False
                    newInternalInputs = UniqList()
                    predInternalInputs = UniqList()
                    for u in self.inputsDict[i]:
                        # the input can actually be input of bouth new clusters
                        # we have to check all in order to build newInputsDict and predCluster.inputDict
                        if u.obj in self.nodes:
                            if not added0:
                                newInputs.append(i)
                                added0 = True
                            newInternalInputs.append(u)
                        if u.obj in predCluster.nodes:
                            if not added1:
                                predCluster.inputs.append(i)
                                added1 = True
                            predInternalInputs.append(u)

                    self.inputsDict[i] = newInternalInputs
                    predCluster.inputsDict[i] = predInternalInputs
                    
                self.inputs = newInputs
                # nodes and outputs can not be shared
                self.nodes = UniqList(n for n in self.nodes if n not in predCluster.nodes)
                newOutputs: UniqList[HlsOperationOut] = UniqList()
                for o in self.outputs:
                    if o.obj in self.nodes:
                        newOutputs.append(o)
                    else:
                        predCluster.outputs.append(o)
                self.outputs = newOutputs
                # new inputs/outputs are generated because we cut the cluster
                for n in self.nodes:
                    for i, dep in zip(n._inputs, n.dependsOn):
                        if dep.obj in predCluster.nodes:
                            o = dep.obj._outputs[dep.out_i]
                            inputsForOutput = self.inputsDict.get(o, None)
                            if inputsForOutput is None:
                                inputsForOutput = self.inputsDict[o] = UniqList()
                            if i not in inputsForOutput:
                                inputsForOutput.append(i) 
                                assert o not in predCluster.outputs
                                predCluster.outputs.append(o)
                
                yield from predCluster.splitToPreventOuterCycles()
                yield self
                return 

        yield self
                
            
class HlsNetlistNodeBitwiseOps(AbstractHlsOp):
    """
    Container of cluster of bitwise operators.
    """

    def __init__(self, parentHls:"HlsPipeline", subNodes: HlsNetlistClusterSearch, name:str=None):
        AbstractHlsOp.__init__(self, parentHls, name=name)
        self._subNodes = subNodes
        for _ in subNodes.inputs:
            self._add_input()
        for _ in subNodes.outputs:
            self._add_output()
        self._totalInputCnt: Dict[HlsOperation, int] = {}

    def resolve_subnode_realization(self, node: HlsOperation, input_cnt: int):
        hls = self.hls
        clk_period = hls.clk_period
        bit_length = node.bit_length

        if node.operator is AllOps.TERNARY:
            input_cnt = input_cnt // 2 + 1

        r = hls.platform.get_op_realization(
            node.operator, bit_length,
            input_cnt, clk_period)
        inp_latency = []
        assert len(node._inputs) >= len(node.dependsOn), (len(node._inputs), node.dependsOn)
        for dep in node.dependsOn:
            dep: HlsOperationOut
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

    def scheduleAsapWithQuantization(self, node: HlsOperation, clk_period: float, pathForDebug: Optional[UniqList["AbstractHlsOp"]]):
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

    def scheduleAsap(self, clk_period: float, pathForDebug: Optional[UniqList["AbstractHlsOp"]]) -> List[float]:
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
                o: HlsOperationOut
                _scheduleOut, _ = self.scheduleAsapWithQuantization(o.obj, clk_period, pathForDebug)
                scheduleOut.append(_scheduleOut[0])
            self.asap_start = tuple(dep.obj.asap_end[dep.out_i] for dep in self.dependsOn)
            self.asap_end = tuple(scheduleOut)
            # input_times = (d.obj.scheduleAsap(clk_period, pathForDebug)[d.out_i] for d in self.dependsOn)
            # schedule nodes using ASAP but use total number of inputs
            # to compute delay for whole subgraph instead just adding time from individual nodes
        
            # the problem is that this cluster may have more than a single output, that means that there is some shared subexpression
            # this subexpression could be potentially evaluated in different times for a different output.
            # If this is the case we need to use minimal time and optionally reset the the colapsing if the time difference is too large
            # between the time when shared subexpression result is evaluate and the time when other inputs are available 
        
        return self.asap_end

    def allocate_instance(self,
            allocator:"HlsAllocator",
            used_signals: SignalsOfStages):
        """
        Instantiate layers of bitwise operators. (Just delegation to sub nodes)
        """
        for outerO, o, t in zip(self._outputs, self._subNodes.outputs, self.scheduledOut):
            outerO: HlsOperationOut
            o: HlsOperationOut
            if outerO in allocator.node2instance:
                # this node was already allocated
                return

            o = allocator.instantiateHlsOperationOut(o, used_signals)
            allocator._registerSignal(outerO, o, used_signals.getForTime(t))

    def __repr__(self, minify=False):
        return f"<{self.__class__.__name__:s} {self._id:d} {[n._id for n in self._subNodes.nodes]}>"


class HlsNetlistPassAggregateBitwiseOps(HlsNetlistPass):
    """
    Extract cluster of bitwise operators as a single node to simplify scheduling.
    """

    def _isBitwiseOperator(self, n: AbstractHlsOp):
        return isinstance(n, HlsOperation) and n.operator in BITWISE_OPS
        
    def apply(self, hls: "HlsStreamProc", to_hw: "SsaSegmentToHwPipeline"):
        bitwiseOpsClusters: List[HlsNetlistClusterSearch] = []
        seen: Set[HlsOperation] = set()
        # discovert clusters of bitwise operators
        for n in to_hw.hls.nodes:
            if n not in seen and self._isBitwiseOperator(n):
                    cluster = HlsNetlistClusterSearch()
                    cluster.discover(n, seen, self._isBitwiseOperator)
                    if len(cluster.nodes) > 1:
                        for c in cluster.splitToPreventOuterCycles():
                            if len(c.nodes) > 1:
                                bitwiseOpsClusters.append(c)

        removedNodes: Set[AbstractHlsOp] = set()
        for cluster in bitwiseOpsClusters:
            cluster: HlsNetlistClusterSearch
            clusterNode = HlsNetlistNodeBitwiseOps(to_hw.hls, cluster)
            cluster.substituteWithNode(clusterNode)
            to_hw.hls.nodes.append(clusterNode)
            removedNodes.update(cluster.nodes)

        to_hw.hls.nodes = [n for n in to_hw.hls.nodes if n not in removedNodes]
