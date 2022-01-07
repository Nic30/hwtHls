from typing import List, Set, Dict, Callable

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.ops import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes


class HlsNetlistClusterSearch():
    """
    This class implements bidirectional floding of the net while predicate is satisfied.
    Collects nodes and inputs/outputs, has methods for manipulation with selection.
    """

    def __init__(self):
        # output ports of outside nodes
        self.inputs: List[HlsNetNodeOut] = []
        self.inputsDict: Dict[HlsNetNodeOut, UniqList[HlsNetNodeIn]] = {}
        # output ports of inside nodes
        self.outputs: UniqList[HlsNetNodeOut] = UniqList()
        self.nodes: UniqList[HlsNetNode] = UniqList()
        
    def _discover(self, n: HlsNetNode, seen: Set[HlsNetNode],
                 predicateFn: Callable[[HlsNetNode], bool]):
        """
        :attention: the inuts and outputs may by falsely detected if there are connections
            which are crossing the layers of the circuit (which usually the case)
        """
        self.nodes.append(n)
        seen.add(n)
        for inp, dep in zip(n._inputs, n.dependsOn):
            dep: HlsNetNodeOut
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
                u: HlsNetNodeIn
                uObj = u.obj
                if uObj not in seen and predicateFn(uObj):
                    self._discover(uObj, seen, predicateFn)            
                else:
                    if outp not in self.outputs:
                        self.outputs.append(outp)

    def discover(self, n: HlsNetNode, seen: Set[HlsNetNode],
                 predicateFn: Callable[[HlsNetNode], bool]):
        """
        Discover the cluster from the node n.
        """
        self._discover(n, seen, predicateFn)
        self.inputs = [i for i in self.inputs if i.obj not in self.nodes]
        # self.outputs = [o for o in self.outputs if o.obj not in self.nodes]
    
    def substituteWithNode(self, n: HlsNetNode):
        """
        Substitute all nodes with the cluster with a single node. All nodes are removed from netlists and disconnected on outer side.
        On inner side the information about connection is kept.
        """
        assert len(self.inputs) == len(n._inputs)
        assert len(self.outputs) == len(n._outputs)
        for boundaryIn, outerOutput in zip(n._inputs, self.inputs):
            outerOutput: HlsNetNodeOut
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
    
    def doesOutputLeadsToInputOfCluster(self, node: HlsNetNode,
                                        seenNodes: Set[HlsNetNodeOut]) -> bool:
        """
        Transitively check if the node outputs leads to some input of this cluster.
        """
        seenNodes.add(node)
        # print(node)
        for o, usedBy in zip(node._outputs, node.usedBy):
            o: HlsNetNodeOut
            for u in usedBy:
                u: HlsNetNodeIn
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

    def collectPredecesorsInCluster(self, node: HlsNetNode):
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
            outputsCausingLoop: List[HlsNetNodeOut] = []
            for o in self.outputs:
                seenNodes: Set[HlsNetNode] = set()
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
                newOutputs: UniqList[HlsNetNodeOut] = UniqList()
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
