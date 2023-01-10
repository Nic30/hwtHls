from itertools import chain
from typing import List, Set, Dict, Tuple, Union

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isNonData
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.analysis.syncDomains import HlsNetlistAnalysisPassSyncDomains
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick


class BetweenSyncNodeIsland():
    """
    An island of nodes between HlsNetNodeExplicitSync nodes (HlsNetNodeRead and HlsNetNodeWrite are subclasses)
    
    :note: inputs/outputs are not related to a read/write operations, it is related how node is positioned relatively to this cluster. 
    :note: control output means that it drives behavior of some output channel, data output may be also control output

    Specific cases of input output relations:
    * inputs and outputs are not inside of nodes
    * nodes may be empty
    * island may not have inputs or outputs but must have at least one
    * each input is input only of a single island
    * each output is output of a single node
    * in input is also an output it means that the node is somewhere in the middle of the island
    """

    def __init__(self, inputs: UniqList[HlsNetNodeExplicitSync],
                 controlOutputs: UniqList[HlsNetNodeExplicitSync],
                 dataOutputs: UniqList[HlsNetNodeExplicitSync],
                 nodes: UniqList[HlsNetNode]):
        assert inputs or controlOutputs or dataOutputs
        self.inputs = inputs
        self.dataOutputs = dataOutputs
        self.controlOutputs = controlOutputs
        self.nodes = nodes
    
    def __repr__(self):
        return f"<{self.__class__.__name__:s} i={[n._id for n in self.inputs]} controlO={[n._id for n in self.controlOutputs]} dataO={[n._id for n in self.dataOutputs]} nodes={len(self.nodes)}>"


class HlsNetlistAnalysisPassSyncReach(HlsNetlistAnalysisPass):
    """
    Discover islands of nodes between the HlsNetNodeExplicitSync nodes.
    
    :note: HlsNetlistAnalysisPassSyncDomains is a different thing because it discovers groups of HlsNetNodeExplicitSync nodes
        tied together with some combinational control dependency.
    
    :note: Sync dependencies (HlsNetNodeExplicitSync extraCond and skipWhen) are treated
        as a part of the HlsNetNodeExplicitSync node successor cluster.
        The rationale behind it that mentioned sync dependencies are controlling flow on input channel
        and this control must be part of this cluster because it decides behavior of this cluster.
    """

    def __init__(self, netlist:"HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.syncIslands: List[BetweenSyncNodeIsland] = []
        # :note: HlsNetNodeExplicitSync nodes have tuple of islands (island where this node is input, island where this node is output)
        self.syncIslandOfNode: Dict[HlsNetNode, Union[BetweenSyncNodeIsland,
                                                      Tuple[None, BetweenSyncNodeIsland],
                                                      Tuple[BetweenSyncNodeIsland, None],
                                                      Tuple[BetweenSyncNodeIsland, BetweenSyncNodeIsland]
                                                      ]] = {}
    
    def _markPrivateInputsAsSeen(self, isl:BetweenSyncNodeIsland,
                                 potentiallyPrivateInputs: List[HlsNetNodeExplicitSync],
                                 seen: Set[HlsNetNode]):
        """
        for those inputs which are only connected to this island we want to mark them as seen
        so we do not try to search for this same cluster again from this node
        """
        inputs = isl.inputs
        nodes = isl.nodes
        controlOutputs = isl.controlOutputs
        dataOutputs = isl.dataOutputs
       
        for pi in potentiallyPrivateInputs:
            pi: HlsNetNodeExplicitSync
            connectedOnlyToThisIsland = True
            for dep in pi.dependsOn:
                if HdlType_isNonData(dep._dtype):
                    continue
                depO = dep.obj
                if depO not in inputs and depO not in nodes and depO not in controlOutputs and depO not in dataOutputs:
                    connectedOnlyToThisIsland = False
                    break

            if not connectedOnlyToThisIsland:
                break
            
            for o, uses in zip(pi._outputs, pi.usedBy):
                if HdlType_isNonData(o._dtype):
                    continue

                for u in uses:
                    useO = u.obj
                    if useO not in inputs and useO not in nodes and useO not in controlOutputs and useO not in dataOutputs:
                        connectedOnlyToThisIsland = False
                        break
                if not connectedOnlyToThisIsland:
                    break

            if connectedOnlyToThisIsland:
                seen.add(pi)
        
    def _flodNetUntilSyncNode(self, beginInput: HlsNetNodeExplicitSync, seen: Set[HlsNetNode]):
        inputs = UniqList([beginInput])
        controlOutputs = UniqList()
        dataOutputs = UniqList()
        nodes = UniqList()
        potentiallyPrivateInputs: List[HlsNetNodeExplicitSync] = []
        
        toSearch: UniqList[HlsNetNode] = UniqList([beginInput, ])
        while toSearch:
            n = toSearch.pop()
            n: HlsNetNode
            if n in seen:
                continue
            isControlOutput = n in controlOutputs 
            isDataOutput = n in dataOutputs 
            isOutput = isControlOutput or isDataOutput
            isInput = n in inputs

            if not isOutput or not any(not HdlType_isNonData(o._dtype) and uses for o, uses in zip(n._outputs, n.usedBy)):
                # not for outputs because we want outputs to be searched again as an input of some other cluster
                seen.add(n)
            elif isInput:
                potentiallyPrivateInputs.append(n)
                
            # search also successors
            deps = n.dependsOn
            if isInput or (isControlOutput and not isDataOutput):
                deps = (d for d, i in zip(n.dependsOn, n._inputs)
                        if i is n.extraCond or i is n.skipWhen)
            elif not isControlOutput and isDataOutput:
                deps = (d for d, i in zip(n.dependsOn, n._inputs)
                        if i is not n.extraCond and i is not n.skipWhen)

            for dep in deps:
                dep: HlsNetNodeOut
                if HdlType_isNonData(dep._dtype):
                    # skip non data dependencies
                    continue
                depO = dep.obj
                if depO in seen or depO in toSearch:
                    continue

                if isinstance(depO, HlsNetNodeExplicitSync):
                    inputs.append(depO)
                    if depO in dataOutputs or depO in controlOutputs:
                        seen.add(depO)
                else:
                    nodes.append(depO)
                toSearch.append(depO)

            if not isOutput:
                for nO, uses in zip(n._outputs, n.usedBy):
                    if HdlType_isNonData(nO._dtype):
                        # skip non data dependencies
                        continue
                    
                    for u in uses:
                        u: HlsNetNodeIn
                        uO = u.obj
                        if uO in seen or uO in toSearch:
                            continue

                        if isinstance(uO, HlsNetNodeExplicitSync):
                            if u is uO.extraCond or u is uO.skipWhen:
                                controlOutputs.append(uO)
                                dataDep = uO.dependsOn[0].obj
                                if isinstance(dataDep, HlsNetNodeConst):
                                    # if this is a write of the constant add constant to this island as well
                                    nodes.append(dataDep)
                                    seen.add(dataDep)
                            else:
                                dataOutputs.append(uO)

                            if uO in inputs:
                                seen.add(uO)
     
                        else:
                            nodes.append(uO)
                        toSearch.append(uO)

        isl = BetweenSyncNodeIsland(inputs, controlOutputs, dataOutputs, UniqList(n for n in nodes if n not in inputs))
        self._markPrivateInputsAsSeen(isl, potentiallyPrivateInputs, seen)
        return isl
            
    def run(self):
        """
        discover clusters of nodes which are definitely a consecutive cluster with HlsNetNodeExplicitSync nodes on its boundaries
        """
        seen = set()
        netlist = self.netlist
        syncIslands = self.syncIslands
        for n in self.netlist.iterAllNodes():
            if n not in seen and isinstance(n, HlsNetNodeExplicitSync):
                island = self._flodNetUntilSyncNode(n, seen)
                syncIslands.append(island)

        # generate syncIslandOfNode dict
        syncIslandOfNode = self.syncIslandOfNode
        for island in syncIslands:
            island:BetweenSyncNodeIsland
            for n in island.inputs:
                (iIsl, oIsl) = syncIslandOfNode.get(n, (None, None))
                assert iIsl is None, ("node can be input only of one island", n, iIsl, island)
                iIsl = island
                syncIslandOfNode[n] = (iIsl, oIsl)

            for n in island.nodes:
                assert n not in syncIslandOfNode
                syncIslandOfNode[n] = island

            for n in chain(island.controlOutputs, island.dataOutputs):
                n: HlsNetNode
                if not any(not HdlType_isNonData(o._dtype) and uses
                           for o, uses in zip(n._outputs, n.usedBy)):
                    (iIsl, oIsl) = syncIslandOfNode.get(n, (None, None))
                    assert oIsl is None, ("node can be output from only of one island", n, oIsl, island)
                    # [fixme] if output is assigned to predecessor node because it has no dependencies
                    # it is required to remove it from the successor
                    oIsl = island
                    syncIslandOfNode[n] = (iIsl, oIsl)

        # previous step may omit some nodes which are mix of control and data path
        # because association to a cluster is ambiguous
        # Sync domains are used to fill nodes to a connected cluster which uses same sync
        if len(seen) != len(netlist.inputs) + len(netlist.nodes) + len(netlist.outputs):
            syncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
            for n in self.netlist.iterAllNodes():
                if n not in seen:
                    searchFromDef = None
                    n1 = n
                    while True:
                        if searchFromDef is not None:
                            syncIsl = syncIslandOfNode.get(n1)
                            if syncIsl is not None:
                                if isinstance(syncIsl, tuple):
                                    if searchFromDef:
                                        isl, _ = syncIsl
                                        if isl is None:
                                            _, isl = syncIsl
                                    else:
                                        _, isl = syncIsl
                                        if isl is None:
                                            isl, _ = syncIsl
                                else:
                                    isl = syncIsl
                                
                                if n not in isl.inputs:
                                    isl.nodes.append(n)
                                syncIslandOfNode[n] = isl
                                break
                                
                        syncDomain = syncDomains.syncOfNode[n1]
                        if len(syncDomain) == 1:
                            associatedSync = tuple(syncDomain)[0]
                            iIsland, _ = syncIslandOfNode[associatedSync]
                            if n not in iIsland.inputs:
                                iIsland.nodes.append(n)
                            syncIslandOfNode[n] = iIsland
                            break

                        elif not n1._inputs:
                            _n1 = None
                            for uses in n1.usedBy:
                                if uses:
                                    _n1 = uses[0].obj
                                    break
                            if _n1 is None:
                                raise AssertionError("Do not know where to continue search on ", n1, " because it has no uses")
                            else:
                                n1 = _n1
                            searchFromDef = True
                            continue

                        elif isinstance(n1, HlsNetNodeDelayClkTick):
                            n1 = n1.dependsOn[0].obj
                            searchFromDef = False
                            continue

                        else:
                            raise NotImplementedError(n1, syncDomain)

        # :note: if there is some additional IO of the cluster which is not just regular read/write
        #  and require some specific channel control it is always as an independent cluster.
        #  and each IO must already be in some cluster.
        #  This means that the query for irregular IO channels is just query for clusters.
        removedIslands = set()
        for isl in syncIslands:
            if not isl.inputs and not isl.nodes and not isl.controlOutputs and not isl.dataOutputs:
                removedIslands.add(isl)
            elif len(isl.inputs) == 1 and (not isl.nodes or (len(isl.nodes) == 1 and isl.inputs[0]._associatedReadSync is isl.nodes[0])):
                # it is guaranteed that there is just a single successor otherwise this island would have more nodes
                inp = isl.inputs[0]
                if any(not HdlType_isNonData(dep._dtype) for dep in inp.dependsOn):
                    # skip this because it has some transitive inputs
                    continue

                if isl.nodes:
                    sucNode = isl.nodes[0].usedBy[0][0].obj
                else:
                    sucNode = None
                    for o, uses in zip(inp._outputs, inp.usedBy):
                        if HdlType_isNonData(o._dtype):
                            continue
                        if uses:
                            sucNode = uses[0].obj
                    if sucNode is None:
                        # this input node has no successors and thus its island can not be merged
                        continue

                if sucNode in isl.inputs or sucNode in isl.nodes:
                    # can not merge with itself
                    continue
                 
                assert sucNode is not None, inp
                sucIsland = syncIslandOfNode[sucNode]
                assert sucIsland is not isl
                if isinstance(sucIsland, tuple):
                    _sucIsland, sucIslandOut = sucIsland
                    if _sucIsland is None:
                        assert sucIslandOut is isl
                        # can not merge with itself (output private only to this island)
                        continue
                    sucIsland = _sucIsland

                assert sucIsland not in removedIslands
                removedIslands.add(isl)
                for n in chain(isl.inputs, isl.nodes):
                    syncIslandOfNode[n] = sucIsland
                sucIsland.inputs.extend(isl.inputs)
                sucIsland.nodes.extend(isl.nodes)
        
        for n, isl in syncIslandOfNode.items():
            assert isl not in removedIslands, n
        syncIslands[:] = (i for i in syncIslands if i not in removedIslands) 
 
        # if cluster contains only HlsNetNodeExplicitSync and optional HlsNetNodeReadSync
        # and has only successor or only predecessor it can be merged into it
 
        # clusters which do have just 1 predecessor can be merged
        #   1 -> 2 -> 3         1,2 -> 3
        #         |-> 4            |-> 4

        # concurrently executable branches may be merged if they do have same successor and no other predecessor
        #   1 -> 2 --> 4    1 -> 2|3 -> 4
        #    |-> 3 -| 

