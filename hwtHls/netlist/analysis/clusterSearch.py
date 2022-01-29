from typing import List, Set, Dict, Callable

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.node import HlsNetNode
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
        self.inputsDict = {k: v for k, v in self.inputsDict.items() if k.obj not in self.nodes}
        # self.outputs = [o for o in self.outputs if o.obj not in self.nodes]
        self.consystencyCheck()
    
    def substituteWithNode(self, n: HlsNetNode):
        """
        Substitute all nodes with the cluster with a single node. All nodes are removed from netlists and disconnected on outer side.
        On inner side the nodes are connected to input of new node.
        """
        assert len(self.inputs) == len(n._inputs)
        assert len(self.outputs) == len(n._outputs)
        for boundaryIn, outerOutput in zip(n._inputs, self.inputs):
            outerOutput: HlsNetNodeOut
            # assert outerOutput.obj in outerOutput.obj.hls.nodes or outerOutput.obj in outerOutput.obj.hls.inputs or outerOutput.obj in outerOutput.obj.hls.outputs, outerOutput
            internInputs = self.inputsDict[outerOutput]
            usedBy = outerOutput.obj.usedBy[outerOutput.out_i]
            usedBy = outerOutput.obj.usedBy[outerOutput.out_i] = [
                i
                for i in usedBy
                if i not in internInputs
            ]
            link_hls_nodes(outerOutput, boundaryIn)
            for i in internInputs:
                i.obj.dependsOn[i.in_i] = boundaryIn
        
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

    def consystencyCheck(self):
        assert len(self.inputs) == len(set(self.inputs)), [(o.obj._id, o.out_i) for o in self.inputs]
        assert len(self.inputsDict) == len(self.inputs), (
            [(o.obj._id, o.out_i) for o in self.inputsDict.keys()],
            [(o.obj._id, o.out_i) for o in self.inputs])

    def updateOuterInputs(self, outerInputMap: Dict[HlsNetNodeOut, HlsNetNodeOut]):
        for i_i, i in enumerate(self.inputs):
            oi = outerInputMap.get(i, i)
            if oi is not i:
                self.inputs[i_i] = oi
                self.inputsDict[oi] = self.inputsDict.pop(i)
        
    def splitToPreventOuterCycles(self):
        """
        If the cluster construction resulted into an outer cycle cut this cluster so the cycle dissapears.
        """
        self.consystencyCheck()
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
                # nodes and outputs can not be shared
                self.nodes = UniqList(n for n in self.nodes if n not in predCluster.nodes)

                # construct new inputs and inputsDict for self and predCluster
                newInputs = []
                newInputsDict = {}
                for outerInp in self.inputs:
                    added0 = False
                    added1 = False
                    newInternalInputs = UniqList()
                    predInternalInputs = UniqList()
                    for internInp in self.inputsDict[outerInp]:
                        internInp: HlsNetNodeOut
                        # the input can actually be input of bouth new clusters
                        # we have to check all in order to build newInputsDict and predCluster.inputDict
                        if internInp.obj in self.nodes:
                            assert internInp.obj not in predCluster.nodes
                            if not added0:
                                newInputs.append(outerInp)
                                added0 = True
                            newInternalInputs.append(internInp)
                        elif internInp.obj in predCluster.nodes:
                            if not added1:
                                predCluster.inputs.append(outerInp)
                                added1 = True
                            predInternalInputs.append(internInp)

                    if newInternalInputs:
                        newInputsDict[outerInp] = newInternalInputs
                    if predInternalInputs:
                        assert outerInp not in predCluster.inputsDict, outerInp
                        predCluster.inputsDict[outerInp] = predInternalInputs
                    
                self.inputs = newInputs
                self.inputsDict = newInputsDict

                # construct new outputs for self and predCluster
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
                            inputsDependentOnOutput = self.inputsDict.get(o, None)
                            if inputsDependentOnOutput is None:
                                inputsDependentOnOutput = self.inputsDict[o] = UniqList()
                                self.inputs.append(o)

                            if i not in inputsDependentOnOutput:
                                inputsDependentOnOutput.append(i) 
                                # assert o not in predCluster.outputs, o
                                predCluster.outputs.append(o)
                
                self.consystencyCheck()
                yield from predCluster.splitToPreventOuterCycles()
                yield self  # self is guaranted to not have outer cycle because we removed all outputs which caused such a thing
                return

        self.consystencyCheck()
        yield self
