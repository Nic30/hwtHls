from itertools import chain
from typing import Set, Tuple

from hwt.hdl.operatorDefs import AllOps
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.betweenSyncIslandsUtils import BetweenSyncIsland, \
    BetweenSyncIsland_getScheduledClkTimes
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopGate import HlsLoopGate, HlsLoopGateStatus
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassBetweenSyncIslandsMerge(HlsNetlistPass):
    """
    Iter all islands and merge all trivial cases to predecessor or successor island.
    """
        
    def _joinIslands(self, srcIsl: BetweenSyncIsland, dstIsl: BetweenSyncIsland, removedIslands: Set[BetweenSyncIsland]):
        """
        Transfer all nodes from srcIsl to dstIsl update syncIslandOfNode dict and remove srcIsl.

        :attention: dstIsl must not be successor of srcIsl (may be predecessor or parallel to)
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

        dstIsl.inputs.extend(i for i in srcIsl.inputs if i not in dstIsl.outputs)
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
        
    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx):

        syncNodes = netlist.getAnalysisIfAvailable(HlsNetlistAnalysisPassBetweenSyncIslands)
        assert syncNodes is not None, "HlsNetlistAnalysisPassBetweenSyncIslands analysis not present at all"
        
        self.syncIslands = syncIslands = syncNodes.syncIslands
        self.syncIslandOfNode = syncIslandOfNode = syncNodes.syncIslandOfNode
        clkPeriod = netlist.normalizedClkPeriod
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
                hasNodesWhichTakeTime: bool = False
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
                        self._joinIslands(predIslands[0], isl, removedIslands)
                        change = True
                    else:
                        for predIsl in predIslands:
                            if predIsl in sucIslands:
                                # if this island depends on some other islad at the begin and at the end
                                # there is no point in keeping it as a separate thread.
                                self._joinIslands(predIsl, isl, removedIslands)
                                change = True
                                break
                        if change:
                            continue
                        # merge to some successor or predecessor which is scheduled to same clock cycle
                        schedTimes = BetweenSyncIsland_getScheduledClkTimes(isl, clkPeriod)
                        for otherIsl, isPred in chain(((i, True) for i in predIslands), ((i, False) for i in sucIslands)):
                            otherSchedTimes = BetweenSyncIsland_getScheduledClkTimes(otherIsl, clkPeriod)
                            if schedTimes.issubset(otherSchedTimes):
                                if isPred:
                                    self._joinIslands(isl, otherIsl, removedIslands)
                                else:
                                    self._joinIslands(otherIsl, isl, removedIslands)
                                    
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
                            self._joinIslands(sucIsl, isl, removedIslands)
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
