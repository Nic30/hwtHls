from typing import List, Set, Dict, Callable

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut, \
    link_hls_nodes
from hwtHls.netlist.observableList import ObservableList


class HlsNetlistClusterSearch():
    """
    This class implements bidirectional flooding of the net while predicate is satisfied.
    Collects nodes and inputs/outputs, has methods for manipulation with selection.
    
    :ivar inputs: all external outputs which are inputs of this cluster
    :ivar inputsDict: maps the external output to all connected inputs in this cluster
    :ivar outputs: all internal outputs which are also outputs of this cluster
    :ivar nodes: all nodes in this cluster
    """

    def __init__(self):
        self.inputs: List[HlsNetNodeOut] = []
        self.inputsDict: Dict[HlsNetNodeOut, UniqList[HlsNetNodeIn]] = {}
        self.outputs: UniqList[HlsNetNodeOut] = UniqList()
        self.nodes: UniqList[HlsNetNode] = UniqList()

    def destroy(self):
        """
        Delete properties of this object to prevent unintentional use.
        """
        self.inputs = None
        self.inputsDict = None
        self.outputs = None
        self.nodes = None
        
    def _discover(self, n: HlsNetNode, seen: Set[HlsNetNode],
                 predicateFn: Callable[[HlsNetNode], bool]):
        """
        :attention: the inputs and outputs may by falsely detected if there are connections
            which are crossing the layers of the circuit (which usually the case)
        """
        self.nodes.append(n)
        seen.add(n)
        for inp, dep in zip(n._inputs, n.dependsOn):
            dep: HlsNetNodeOut
            assert dep is not None, ("Disconnected input", inp)
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
                if uObj in seen:
                    continue
                elif predicateFn(uObj):
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
        self.inputs = ObservableList(i for i in self.inputs if i.obj not in self.nodes)
        self.inputsDict = {k: v for k, v in self.inputsDict.items() if k.obj not in self.nodes}
        # self.outputs = [o for o in self.outputs if o.obj not in self.nodes]
        self.consystencyCheck()

    @classmethod
    def discoverFromNodeList(cls, nodeList: List[HlsNetNode]):
        self = cls()
        # self.inputs: List[HlsNetNodeOut] = []
        # self.inputsDict: Dict[HlsNetNodeOut, UniqList[HlsNetNodeIn]] = {}
        # self.outputs: UniqList[HlsNetNodeOut] = UniqList()
        # self.nodes: UniqList[HlsNetNode] = UniqList()
        inputs = self.inputs
        inputsDict = self.inputsDict
        outputs = self.outputs
        nodes = self.nodes
        nodes.extend(nodeList)
        for n in nodeList:
            for i, dep in zip(n._inputs, n.dependsOn):
                if dep.obj not in nodes:
                    internOutUsers = inputsDict.get(dep, None)
                    if internOutUsers is None:
                        internOutUsers = inputsDict[dep] = UniqList()
                        inputs.append(dep)
                    internOutUsers.append(i)
            for o, uses in zip(n._outputs, n.usedBy):
                if any(u.obj not in nodes for u in uses):
                    outputs.append(o)
        return self

    def substituteWithNode(self, n: HlsNetNodeAggregate):
        """
        Substitute all nodes with the cluster with a single node. All nodes are removed from netlists and disconnected on outer side.
        On inner side the nodes are connected to input of new node.
        """
        assert not n._inputs, (n, "Inputs are added in this function")
        assert not n._outputs, (n, "Outputs are added in this function")

        for outerOutput in self.inputs:
            outerOutput: HlsNetNodeOut
            boundaryIn, boundaryInPort = n._addInput(outerOutput._dtype, outerOutput.name)
            # assert outerOutput.obj in outerOutput.obj.hls.nodes or outerOutput.obj in outerOutput.obj.hls.inputs or outerOutput.obj in outerOutput.obj.hls.outputs, outerOutput
            internInputs = self.inputsDict[outerOutput]
            oldUsedBy = outerOutput.obj.usedBy[outerOutput.out_i]
            usedBy = outerOutput.obj.usedBy[outerOutput.out_i] = [
                i
                for i in oldUsedBy
                if i not in internInputs
            ]
            link_hls_nodes(outerOutput, boundaryIn)
            portUses = boundaryInPort.obj.usedBy[0]
            for i in internInputs:
                i.obj.dependsOn[i.in_i] = boundaryInPort
                portUses.append(i)

        clusterNodes = self.nodes
        for interOutput in self.outputs:
            # disconnect interOutput from all external inputs
            # and connect them to boundary output of node
            
            # if this is also an output from parent cluster
            # it should have only 
            
            boundaryOut, boundaryOutPort = n._addOutput(interOutput._dtype, interOutput.name)
            # reconnect all external uses to a port on this aggregate
            newUsedBy = n.usedBy[boundaryOut.out_i]
            usedBy = interOutput.obj.usedBy[interOutput.out_i]
            for in_ in usedBy:
                if in_.obj not in clusterNodes:
                    in_.obj.dependsOn[in_.in_i] = boundaryOut
                    newUsedBy.append(in_)

            # filter connection of interOutput to contain only connection to in cluster nodes and  boundaryOutPort 
            assert newUsedBy, (boundaryOut, "If the port is unused outside of cluster it should not be in cluster boundary at the first place")
            newInterUses = [
                in_ for in_ in usedBy
                if in_.obj in clusterNodes]
            newInterUses.append(boundaryOutPort)
            interOutput.obj.usedBy[interOutput.out_i] = newInterUses
            boundaryOutPort.obj.dependsOn[0] = interOutput

        # remove because the information is now store in node "n"
        self.inputs = None
        self.inputsDict = None
        self.outputs = None

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
        for o in self.outputs:
            assert any(u.obj not in self.nodes for u in o.obj.usedBy[o.out_i]), (o, "If this is an output of cluster it must be used outside")
        for i in self.inputs:
            assert i.obj not in self.nodes, ("If this is an input it must originate from outside of cluster")

    def updateOuterInputs(self, outerInputMap: Dict[HlsNetNodeOut, HlsNetNodeOut]):
        for i_i, i in enumerate(self.inputs):
            oi = outerInputMap.get(i, i)
            oi: HlsNetNodeOut
            if oi is not i:
                self.inputs[i_i] = oi
                userList = self.inputsDict[oi] = self.inputsDict.pop(i)
                for u in userList:
                    u: HlsNetNodeIn
                    uObj = u.obj
                    uObj.dependsOn[u.in_i] = oi
                    if isinstance(uObj, HlsNetNodeAggregate):
                        uObj._subNodes.updateOuterInputs(outerInputMap)

    def splitToPreventOuterCycles(self):
        """
        If the cluster construction resulted into an outer cycle cut this cluster so the cycle disappears.
        """
        self.consystencyCheck()
        # >1 because if there was just 1 output the cycle has been there even before this cluster was generated.
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
                yield self  # self is guaranteed to not have outer cycle because we removed all outputs which caused such a thing
                return

        self.consystencyCheck()
        yield self
