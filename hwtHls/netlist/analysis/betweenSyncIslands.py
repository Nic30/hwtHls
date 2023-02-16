from itertools import chain
from typing import List, Set, Dict, Tuple, Union

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.analysis.betweenSyncIslandsUtils import BetweenSyncIsland, BetweenSyncIsland_getScheduledClkTimes
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from ipCorePackager.constants import DIRECTION
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwt.hdl.operatorDefs import AllOps
from hwtHls.netlist.nodes.loopGate import HlsLoopGate, HlsLoopGateStatus
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter


class HlsNetlistAnalysisPassBetweenSyncIslands(HlsNetlistAnalysisPass):
    """
    Discover islands of nodes between the HlsNetNodeExplicitSync nodes.
    
    :note: HlsNetlistAnalysisPassSyncDomains is a different thing because it discovers groups of HlsNetNodeExplicitSync nodes
        tied together with some combinational control dependency.
    :note: HlsNetNodeRead _validNB has a special meaning.
    :note: Sync dependencies (HlsNetNodeExplicitSync extraCond and skipWhen) are treated
        as a part of the HlsNetNodeExplicitSync node successor cluster.
        The rationale behind it that mentioned sync dependencies are controlling flow on input channel
        and this control must be part of this cluster because it decides behavior of this cluster.
    """

    def __init__(self, netlist:"HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.syncIslands: List[BetweenSyncIsland] = []
        # :note: HlsNetNodeExplicitSync nodes have tuple of islands (island where this node is input, island where this node is output)
        self.syncIslandOfNode: Dict[HlsNetNode, Union[BetweenSyncIsland,
                                                      Tuple[None, BetweenSyncIsland],
                                                      Tuple[BetweenSyncIsland, None],
                                                      Tuple[BetweenSyncIsland, BetweenSyncIsland]
                                                      ]] = {}

    def _addNodesFromIslandToSyncIslandOfNodeDict(self, isl: BetweenSyncIsland):
        syncIslandOfNode = self.syncIslandOfNode
        for n in isl.inputs:
            (iIsl, oIsl) = syncIslandOfNode.get(n, (None, None))
            assert iIsl is None, ("node can be input only of one island", n, iIsl, isl)
            iIsl = isl
            syncIslandOfNode[n] = (iIsl, oIsl)

        for n in isl.nodes:
            assert n not in syncIslandOfNode, (n, syncIslandOfNode[n])
            syncIslandOfNode[n] = isl

        for n in isl.outputs:
            n: HlsNetNode
            (iIsl, oIsl) = syncIslandOfNode.get(n, (None, None))
            assert oIsl is None, ("node can be output from only one island", n, oIsl, isl)
            oIsl = isl
            syncIslandOfNode[n] = (iIsl, oIsl)
   
    @classmethod
    def discoverSyncIsland(cls, node: HlsNetNodeExplicitSync, incommingDir: DIRECTION, reachDb: HlsNetlistAnalysisPassReachabilility)\
            ->Tuple[UniqList[HlsNetNodeExplicitSync], UniqList[HlsNetNodeExplicitSync]]: 
        """
        This function search for sync nodes related to specified input node.
        First search for all users of this node outputs
        and then again checks if there are more other sync dependencies and repeats the search
        while new sync nodes are discovered.

        :note: There may be some nodes which are bouth input and output.
        """
        
        # find boundaries of local synchronization cluster
        inputs: UniqList[HlsNetNodeExplicitSync] = UniqList()
        outputs: UniqList[HlsNetNodeExplicitSync] = UniqList()
        toSearchDefToUse: List[HlsNetNode] = []
        toSearchUseToDef: List[HlsNetNode] = []
        seenDefToUse: Set[HlsNetNode] = set()
        seenUseToDef: Set[HlsNetNode] = set()
        internalNodes: UniqList[HlsNetNode] = UniqList()

        if incommingDir == DIRECTION.IN:
            toSearchDefToUse.append(node)
            inputs.append(node)
        else:
            assert incommingDir == DIRECTION.OUT, incommingDir
            toSearchUseToDef.append(node)
            outputs.append(node)

        while toSearchUseToDef or toSearchDefToUse:
            for n in reachDb.getDirectDataSuccessorsMany(toSearchDefToUse):
                # search use -> def (top -> down)
                if n not in seenUseToDef:
                    seenUseToDef.add(n)
                    toSearchUseToDef.append(n)

                if isinstance(n, HlsNetNodeExplicitSync):
                    outputs.append(n)
                else:
                    internalNodes.append(n)
                    
            for n in reachDb.getDirectDataPredecessorsMany(toSearchUseToDef):
                # search use -> def (top -> down)
                if n not in seenDefToUse:
                    seenDefToUse.add(n)
                    toSearchDefToUse.append(n)

                if isinstance(n, HlsNetNodeExplicitSync):
                    inputs.append(n)
                else:
                    internalNodes.append(n)
                    
        # inputs may dependent on outputs because we stop search
        # after first found HlsNetNodeExplicitSync instance 
        iOffset = 0
        for ii, i in tuple(enumerate(inputs)):
            for o in outputs:
                if reachDb.doesReachToData(o, i):
                    _i = inputs.pop(iOffset + ii)
                    assert _i is i
                    outputs.append(i)
                    iOffset -= 1
                    break
          
        return inputs, outputs, internalNodes

    def _collectSyncIslandsByFlooding(self, reachDb: HlsNetlistAnalysisPassReachabilility):
        syncIslandOfNode = self.syncIslandOfNode 
        syncIslands = self.syncIslands

        for n in self.netlist.iterAllNodes():
            if n not in syncIslandOfNode.keys() and isinstance(n, HlsNetNodeIoClusterCore):
                n: HlsNetNodeIoClusterCore
                _inputs = n.usedBy[n.inputNodePort.out_i]
                _outputs = n.usedBy[n.outputNodePort.out_i]
                if _inputs:
                    n0 = _inputs[0].obj
                    d = DIRECTION.IN
                else:
                    n0 = _outputs[0].obj
                    d = DIRECTION.OUT
                inputs, outputs, nodes = self.discoverSyncIsland(n0, d, reachDb)
                nodes.append(n)
                island = BetweenSyncIsland(inputs, outputs, nodes)
                self._addNodesFromIslandToSyncIslandOfNodeDict(island)
                syncIslands.append(island)

    def _joinIslands(self, srcIsl: BetweenSyncIsland, dstIsl: BetweenSyncIsland, removedIslands: Set[BetweenSyncIsland]):
        """
        Transfer all nodes from srcIsl to dstIsl update syncIslandOfNode dict and remove srcIsl.
        """
        # print("_joinIslands", srcIsl, dstIsl)
        assert srcIsl is not dstIsl
        syncIslandOfNode = self.syncIslandOfNode

        assert dstIsl not in removedIslands
        removedIslands.add(srcIsl)
        for n in srcIsl.nodes:
            syncIslandOfNode[n] = dstIsl
        for io in chain(srcIsl.inputs, srcIsl.outputs):
            curSrc, curDst = syncIslandOfNode[io]
            syncIslandOfNode[io] = (dstIsl if curSrc is srcIsl else curSrc,
                                    dstIsl if curDst is srcIsl else curDst)
        dstIsl.inputs.extend(srcIsl.inputs)
        dstIsl.nodes.extend(srcIsl.nodes)
        dstIsl.outputs.extend(srcIsl.outputs)

    def _collectConnectedIslands(self, isl: BetweenSyncIsland) -> Tuple[UniqList[BetweenSyncIsland], UniqList[BetweenSyncIsland]]:
        syncIslandOfNode = self.syncIslandOfNode
        predIslands: UniqList[BetweenSyncIsland] = UniqList()
        sucIslands: UniqList[BetweenSyncIsland] = UniqList()
        for n in chain(isl.inputs, isl.nodes, isl.outputs):
            # no need to check exclude void links as there is no IO and thus void links
            # there are representing data only
            for dep in n.dependsOn:
                predIsl = syncIslandOfNode[dep.obj]
                if isinstance(predIsl, tuple):
                    _, predIsl = predIsl 
                if predIsl is not None:
                    predIslands.append(predIsl)

            for uses in n.usedBy:
                for u in uses:
                    sucIsl = syncIslandOfNode[u.obj]
                    if isinstance(sucIsl, tuple):
                        sucIsl , _ = sucIsl 
                    if sucIsl is not None:
                        sucIslands.append(sucIsl)
        
        predIslands.discard(isl)
        sucIslands.discard(isl)
        return predIslands, sucIslands
        
    def _mergeSyncIslands(self):
        """
        Iter all islands and merge all trivial cases to predecessor or successor island.
        """
        syncIslands = self.syncIslands
        syncIslandOfNode = self.syncIslandOfNode
        # :note: if there is some additional IO of the cluster which is not just regular read/write
        #  and require some specific channel control it is always as an independent cluster.
        #  and each IO must already be in some cluster.
        #  This means that the query for irregular IO channels is just query for clusters.
        removedIslands: Set[BetweenSyncIsland] = set()
        while True:
            change: bool = False
            for isl in syncIslands:
                isl: BetweenSyncIsland
                if isl in removedIslands:
                    continue
                # print(isl)
                hasNodesWhichTakeTime = False
                for n in isl.nodes:
                    if isinstance(n, (HlsNetNodeIoClusterCore, HlsNetNodeConst)):
                        pass
                    elif isinstance(n, HlsNetNodeOperator) and n.operator in (AllOps.INDEX, AllOps.CONCAT):
                        pass
                    elif isinstance(n, (HlsLoopGate, HlsLoopGateStatus, HlsProgramStarter)):
                        pass
                    else:
                        hasNodesWhichTakeTime = True
                        break
                    
                isAllNonBlocking = all(isinstance(i, (HlsNetNodeRead, HlsNetNodeWrite)) and not i._isBlocking for i in isl.inputs)
                hasNoIo = not isl.inputs and not isl.outputs
                if hasNoIo or isAllNonBlocking or not hasNodesWhichTakeTime:
                    predIslands, sucIslands = self._collectConnectedIslands(isl)
                    if len(sucIslands) == 1:
                        self._joinIslands(isl, sucIslands[0], removedIslands)
                        change = True
                    elif len(predIslands) == 1:
                        self._joinIslands(isl, predIslands[0], removedIslands)
                        change = True
                    else:
                        for predIsl in predIslands:
                            if predIsl in sucIslands:
                                # if this island depends on some other islad at the begin and at the end
                                # there is no point in keeping it as a separate thread.
                                self._joinIslands(isl, predIsl, removedIslands)
                                change = True
                                break

                        clkPeriod = self.netlist.normalizedClkPeriod
                        # merge to some successor or predecessor which is scheduled to same clock cycle
                        schedTimes = BetweenSyncIsland_getScheduledClkTimes(isl, clkPeriod)
                        for otherIsl in chain(predIslands, sucIslands):
                            otherSchedTimes = BetweenSyncIsland_getScheduledClkTimes(otherIsl, clkPeriod)
                            if schedTimes.issubset(otherSchedTimes):
                                self._joinIslands(isl, otherIsl, removedIslands)
                                change = True
                                break
    
                elif hasNodesWhichTakeTime:
                    if len(isl.inputs) == 1 and not len(isl.outputs):
                        # merge to predecessor because this cluster has just this out node
                        # which is synchronization itself and thus no additional sync is required
                        inp: HlsNetNodeExplicitSync = isl.inputs[0]
                        predCluster = inp.dependsOn[inp._outputOfCluster.in_i].obj
                        predIsl = syncIslandOfNode[predCluster]
                        if predIsl is not isl:
                            self._joinIslands(isl, predIsl, removedIslands)
                            change = True
                    elif not isl.inputs and len(isl.outputs) == 1:
                        out: HlsNetNodeExplicitSync = isl.outputs[0]
                        sucCluster = out.dependsOn[out._inputOfCluster.in_i].obj
                        sucIsl = syncIslandOfNode[sucCluster]
                        if sucIsl is not isl:
                            self._joinIslands(isl, sucIsl, removedIslands)
                            change = True
            if not change:
                break

        for n, isl in syncIslandOfNode.items():
            assert isl not in removedIslands, (n, isl)
        syncIslands[:] = (i for i in syncIslands if i not in removedIslands) 
 
        # if cluster contains only HlsNetNodeExplicitSync and optional HlsNetNodeReadSync
        # and has only successor or only predecessor it can be merged into it
 
        # clusters which do have just 1 predecessor can be merged
        #   1 -> 2 -> 3         1,2 -> 3
        #         |-> 4            |-> 4

        # concurrently executable branches may be merged if they do have same successor and no other predecessor
        #   1 -> 2 --> 4    1 -> 2|3 -> 4
        #    |-> 3 -| 

    def _collectNodesWithoutIsland(self, node: HlsNetNode, incommingDir: DIRECTION):
        """
        :param direction: DIRECTION.OUT means that the search is performed from this node to up to defs
            DIRECTION.IN is an oposite, from this node down to uses
        """
        # :note: highly similar to discoverSyncIsland
        syncIslandOfNode = self.syncIslandOfNode
        toSearchDefToUse: List[HlsNetNode] = []
        toSearchUseToDef: List[HlsNetNode] = []
        seenDefToUse: Set[HlsNetNode] = set()
        seenUseToDef: Set[HlsNetNode] = set()
        internalNodes: UniqList[HlsNetNode] = UniqList((node,))

        if incommingDir == DIRECTION.IN:
            toSearchDefToUse.append(node)
        elif incommingDir == DIRECTION.OUT:
            toSearchUseToDef.append(node)
        else:
            assert incommingDir == DIRECTION.INOUT, incommingDir
            toSearchDefToUse.append(node)
            toSearchUseToDef.append(node)
        
        resolvedNodes = syncIslandOfNode.keys()
        while toSearchUseToDef or toSearchDefToUse:
            for n in HlsNetlistAnalysisPassReachabilility._getDirectDataSuccessorsRawAnyData(toSearchDefToUse, seenDefToUse, resolvedNodes):
                # search use -> def (top -> down)
                if n not in seenUseToDef:
                    toSearchUseToDef.append(n)
                internalNodes.append(n)
                    
            for n in HlsNetlistAnalysisPassReachabilility._getDirectDataPredecessorsRawAnyData(toSearchUseToDef, seenUseToDef, resolvedNodes):
                # search use -> def (top -> down)
                if n not in seenDefToUse:
                    toSearchDefToUse.append(n)
                internalNodes.append(n)

        return internalNodes

    def _collectLeftOutNodesToOwnIslandsOrMergeIfPossible(self):
        syncIslands = self.syncIslands
        syncIslandOfNode = self.syncIslandOfNode
        for isl in syncIslands:
            isl: BetweenSyncIsland
            for n in chain(isl.inputs, isl.outputs, isl.nodes):
                n: HlsNetNode
                for dep in n.dependsOn:
                    depO = dep.obj
                    depOIsl = syncIslandOfNode.get(depO, None)
                    if depOIsl is None:
                        nodes = self._collectNodesWithoutIsland(depO, DIRECTION.INOUT)
                        isl = BetweenSyncIsland(UniqList(), UniqList(), nodes)
                        syncIslands.append(isl)
                        for n0 in isl.nodes:
                            syncIslandOfNode[n0] = isl

        # syncIslandOfNode = self.syncIslandOfNode
        #    syncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
        #    for n in self.netlist.iterAllNodes():
        #        if n not in seen:
        #            searchFromDef = None
        #            n1 = n
        #            while True:
        #                if searchFromDef is not None:
        #                    syncIsl = syncIslandOfNode.get(n1)
        #                    if syncIsl is not None:
        #                        if isinstance(syncIsl, tuple):
        #                            if searchFromDef:
        #                                isl, _ = syncIsl
        #                                if isl is None:
        #                                    _, isl = syncIsl
        #                            else:
        #                                _, isl = syncIsl
        #                                if isl is None:
        #                                    isl, _ = syncIsl
        #                        else:
        #                            isl = syncIsl
        #                        
        #                        if n not in isl.inputs:
        #                            isl.nodes.append(n)
        #                        syncIslandOfNode[n] = isl
        #                        break
        #                        
        #                syncDomain = syncDomains.syncOfNode[n1]
        #                if len(syncDomain) == 1:
        #                    associatedSync = tuple(syncDomain)[0]
        #                    iIsland, _ = syncIslandOfNode[associatedSync]
        #                    if n not in iIsland.inputs:
        #                        iIsland.nodes.append(n)
        #                    syncIslandOfNode[n] = iIsland
        #                    break
        #
        #                elif not n1._inputs:
        #                    _n1 = None
        #                    for uses in n1.usedBy:
        #                        if uses:
        #                            _n1 = uses[0].obj
        #                            break
        #                    if _n1 is None:
        #                        raise AssertionError("Do not know where to continue search on ", n1, " because it has no uses")
        #                    else:
        #                        n1 = _n1
        #                    searchFromDef = True
        #                    continue
        #
        #                elif isinstance(n1, HlsNetNodeDelayClkTick):
        #                    n1 = n1.dependsOn[0].obj
        #                    searchFromDef = False
        #                    continue
        #                else:
        #                    raise NotImplementedError(n1, syncDomain)    
    def run(self):
        """
        discover clusters of nodes which are definitely a consecutive cluster with HlsNetNodeExplicitSync nodes on its boundaries
        """
        netlist = self.netlist
        reachDb = netlist.getAnalysis(HlsNetlistAnalysisPassReachabilility)
        self._collectSyncIslandsByFlooding(reachDb)
        seen = self.syncIslandOfNode
        if len(seen) != len(netlist.inputs) + len(netlist.nodes) + len(netlist.outputs):
            self._collectLeftOutNodesToOwnIslandsOrMergeIfPossible()
        self._mergeSyncIslands()
        
        for n in self.netlist.iterAllNodes():
            assert n in self.syncIslandOfNode, n
       
