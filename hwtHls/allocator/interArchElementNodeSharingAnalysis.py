from cmath import inf
from typing import Union, List, Dict, Tuple

from hwt.pyUtils.uniqList import UniqList
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut


class InterArchElementNodeSharingAnalysis():
    """
    :ivar interElemConnections: the port tuples which are crossing the boundaries of :class:`hwtHls.allocator.architecturalElement.AllocatorArchitecturalElement`
        instances
    :ivar multiOwnerNodes: a list of nodes which are owned by multiple :class:`hwtHls.allocator.architecturalElement.AllocatorArchitecturalElement` instances
    :ivar nodePartToPort: a dictionary which maps the port of multi part node to a specific part
    :ivar ownerOfNode: a dictionary mapping node to list of :class:`hwtHls.allocator.architecturalElement.AllocatorArchitecturalElement`
        instance
    :ivar partsOfNode: dictionary mapping the node to its parts in individual architecture elements
    :note: if node has multiple owners the owners are using only :class:`hwtHls.netlist.nodes.node.HlsNetNodePartRef` instances and ownerOfNode is also using only parts
        However the port itsef does use original node.
    :ivar ownerOfInput: a dictionary mapping node input to list of :class:`hwtHls.allocator.architecturalElement.AllocatorArchitecturalElement`
        instance
    :ivar ownerOfOutput: a dictionary mapping node output to list of :class:`hwtHls.allocator.architecturalElement.AllocatorArchitecturalElement`
        instance
    :ivar firstUseTimeOfOutInElem: information about when each node output is used in :class:`hwtHls.allocator.architecturalElement.AllocatorArchitecturalElement`
        instance for the first time
    """

    def __init__(self):
        self.interElemConnections: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]] = UniqList()
        self.multiOwnerNodes: UniqList[HlsNetNode] = UniqList()
        self.nodePartToPort: Dict[Union[HlsNetNodeIn, HlsNetNodeOut], HlsNetNodePartRef]
        self.ownerOfNode: Dict[HlsNetNode, AllocatorArchitecturalElement] = {}
        self.partsOfNode: Dict[HlsNetNode, List[HlsNetNodePartRef]] = {}
        self.ownerOfInput: Dict[HlsNetNodeIn, UniqList[AllocatorArchitecturalElement]] = {}
        self.ownerOfOutput: Dict[HlsNetNodeOut, AllocatorArchitecturalElement] = {}
        # because output value could be used in element multiple times but we need only the first use
        self.firstUseTimeOfOutInElem: Dict[Tuple[AllocatorArchitecturalElement, HlsNetNodeOut], float] = {}
        self.portSynonyms: Union[Dict[HlsNetNodeIn, UniqList[HlsNetNodeIn]], Dict[HlsNetNodeOut, UniqList[HlsNetNodeOut]]] = {}

    def _analyzeInterElementsNodeSharingCheckInputDriver(self, o: HlsNetNodeOut, i: HlsNetNodeIn, inT: float, dstElm: AllocatorArchitecturalElement):
        assert dstElm in self.ownerOfInput[i], (dstElm, i, self.ownerOfInput[i])
        oOwner = self.ownerOfOutput[o]
        if dstElm is oOwner:
            return
        # this input is connected to something outside of this arch. element
        firstUseTimeKey = (dstElm, o)
        curT = self.firstUseTimeOfOutInElem.get(firstUseTimeKey, inf)
        if curT > inT:
            # earlier time of use discovered
            self.firstUseTimeOfOutInElem[firstUseTimeKey] = inT
            print("_analyzeInterElementsNodeSharingCheckInputDriver", o, inT)
        self.interElemConnections.append((o, i))
    
    def _addPortSynonym(self, p0, p1):
        syn0 = self.portSynonyms.get(p0, None)
        syn1 = self.portSynonyms.get(p1, None)

        if syn0 is None and syn1 is None:
            syn = self.portSynonyms[p0] = self.portSynonyms[p1] = UniqList()
            syn.append(p0)
            syn.append(p1)
        elif syn0 is None:
            self.portSynonyms[p0] = syn1
            syn1.append(p0)
        elif syn1 is None:
            self.portSynonyms[p1] = syn0
            syn1.append(p1)
        elif len(syn0) < len(syn1):
            syn1.extend(syn0)
            self.portSynonyms[p0] = syn1
        else:
            syn0.extend(syn1)
            self.portSynonyms[p1] = syn0

    def _analyzeInterElementsNodeSharing(self, archElements: List[AllocatorArchitecturalElement]):
        # resolve port and node owners
        for dstElm in archElements:
            dstElm: AllocatorArchitecturalElement
            for n in dstElm.allNodes:
                n: HlsNetNode

                curOwner = self.ownerOfNode.get(n, None)
                if curOwner is None:
                    self.ownerOfNode[n] = dstElm
                else:
                    assert curOwner is dstElm, ("Each node may be only in a single element", n, curOwner, dstElm)

                if isinstance(n, HlsNetNodePartRef):
                    n: HlsNetNodePartRef
                    # print("seen part", n)
                    for e in archElements:
                        assert n.parentNode not in e.allNodes, ("If node is fragmented only parts should be used", n, e)
                    self.partsOfNode.setdefault(n.parentNode, []).append(n)
                    self.multiOwnerNodes.append(n.parentNode)

                    # for extOut in n._subNodes.inputs:
                    #    connectedInputs = n._subNodes.inputsDict.get(extOut, extOut.obj.usedBy[extOut.out_i])
                    #    for i in connectedInputs:
                    #        self.ownerOfInput[i] = dstElm
                    # parentNodeInPortMap = {intern:outer for intern, outer in zip(n.parentNode._subNodes.inputs, n.parentNode._inputs)}
                    # parentNodeOutPortMap = {intern:outer for intern, outer in zip(n.parentNode._subNodes.outputs, n.parentNode._outputs)}
                    for subNode in n._subNodes.nodes:
                        for i in subNode._inputs:
                            assert i not in self.ownerOfInput
                            self.ownerOfInput[i] = UniqList((dstElm,))
                            # for outer inputs of original cluster node we must check oter uses because the owner could be multiple elements
                            # because input could be used in multiple parts
                            outerIn = n.parentNode.outerOutToIn.get(subNode.dependsOn[i.in_i], None)
                            if outerIn is not None:
                                curOwner = self.ownerOfInput.get(outerIn, None)
                                if curOwner is None:
                                    self.ownerOfInput[outerIn] = UniqList((dstElm,))
                                else:
                                    assert isinstance(curOwner, UniqList), curOwner
                                    curOwner.append(dstElm)
                                
                        for o in subNode._outputs:
                            # print("    seen o", o)
                            self.ownerOfOutput[o] = dstElm
                            parOut = n.parentNode.internOutToOut.get(o, None)
                            if parOut is not None:
                                # print("    seen par o", parOut)
                                assert parOut not in self.ownerOfOutput
                                self.ownerOfOutput[parOut] = dstElm
                                # print("adding synonym", dstElm, o, parOut)
                                self._addPortSynonym(o, parOut)
                        
                else: 
                    for i in n._inputs:
                        assert i not in  self.ownerOfInput 
                        self.ownerOfInput[i] = UniqList((dstElm,))

                    for o in n._outputs:
                        assert o not in  self.ownerOfOutput
                        self.ownerOfOutput[o] = dstElm
            
        for dstElm in archElements:
            # for each input check if value originates from other arch element,
            # if it does and was not been resolved yet, declare it on element of origin and add it at starting time to this element 
            dstElm: AllocatorArchitecturalElement
            for n in dstElm.allNodes:
                n: HlsNetNode
                if isinstance(n, HlsNetNodePartRef):
                    n: HlsNetNodePartRef
                    for extOut in n._subNodes.inputs:
                        assert extOut.obj not in n._subNodes.nodes, ("If this is an external input it must not originate from this node", extOut, n, dstElm) 
                        outerIn = n.parentNode.outerOutToIn.get(extOut, None)
                        if outerIn is not None:
                            connectedInputs = n.parentNode._subNodes.inputsDict[extOut]
                        else:
                            connectedInputs = tuple(u for u in extOut.obj.usedBy[extOut.out_i])
                            
                        fistUseTime = None
                        for i in connectedInputs:
                            if i.obj not in n._subNodes.nodes:
                                continue
                            t = i.obj.scheduledIn[i.in_i]
                            o = i.obj.dependsOn[i.in_i]
                            assert o is extOut
                            self._analyzeInterElementsNodeSharingCheckInputDriver(o, i, t, dstElm)
                            if fistUseTime is None or fistUseTime > t:
                                fistUseTime = t
                        assert fistUseTime is not None, ("If it is unused it should not be in inputs at the first place", extOut, n, connectedInputs)
                        if outerIn is not None:
                            self._analyzeInterElementsNodeSharingCheckInputDriver(extOut, outerIn, fistUseTime, dstElm)
                            
                else: 
                    for t, i, o in zip(n.scheduledIn, n._inputs, n.dependsOn):
                        self._analyzeInterElementsNodeSharingCheckInputDriver(o, i, t, dstElm)

