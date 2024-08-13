from itertools import chain
from typing import Set, Tuple, Optional

from hwt.hdl.operatorDefs import HwtOps
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.betweenSyncIslandsUtils import BetweenSyncIsland
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup, \
    LOOP_CHANEL_GROUP_ROLE
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


# from hwtHls.netlist.nodes.loopControlPort import HlsNetNodeLoopEnterRead, \
#    HlsNetNodeLoopEnterWrite, HlsNetNodeLoopExitWrite, HlsNetNodeLoopExitRead
class SyncIslandProps():
    """
    Container of sync island properties.
    """

    def __init__(self):
        self.hasNodesWhichTakeTime: bool = False
        self.unmergableNodes: Tuple[Set[HlsNetNode], Set[HlsNetNode]] = (set(), set())
        self.isAllNonBlocking: bool = True
        self.hasNoIo: bool = True

    @staticmethod
    def _getUnmergableNodes(isl: BetweenSyncIsland) -> Tuple[Set[HlsNetNode], Set[HlsNetNode]]:
        """
        Get sets of nodes which can not be merged to this island.
        
        If some member node is inside of the loop we can not merge with 
        enter writes, exit data/control reads if they are HlsNetNodeReadForwardEdge
        (exit notification to loop status can always be merged because it is backedge)
        
        if some member node is outside of the loop we can not merge with
        with enter/reenter reads exit data writs and read-write pairs for exit notifications
        """
        unmergablePredNodes: Set[HlsNetNode] = set()
        unmergableSucNodes: Set[HlsNetNode] = set()
        for n in isl.iterAllNodes():
            if isinstance(n, HlsNetNodeLoopStatus):
                n: HlsNetNodeLoopStatus
                for g in n.fromEnter:
                    unmergablePredNodes.update(g.members)
                for e in n.fromExitToSuccessor:
                    unmergableSucNodes.update(w.associatedRead for w in e.members
                                              if isinstance(w.associatedRead, HlsNetNodeWriteForwardedge))
            elif isinstance(n, HlsNetNodeReadBackedge):
                g = n.associatedWrite._loopChannelGroup
                if g is not None:
                    g: LoopChanelGroup
                    for loop, role in g.connectedLoops:
                        if role in (LOOP_CHANEL_GROUP_ROLE.ENTER,
                                    LOOP_CHANEL_GROUP_ROLE.REENTER,
                                    LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER):
                            unmergableSucNodes.update(loop.iterChannelIoOutsideOfLoop())
                        else:
                            assert role == LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR
                            unmergableSucNodes.update(loop.iterChannelIoInsideOfLoop())
            elif isinstance(n, HlsNetNodeWriteBackedge):
                g = n._loopChannelGroup
                if g is not None:
                    g: LoopChanelGroup
                    for loop, role in g.connectedLoops:
                        if role in (LOOP_CHANEL_GROUP_ROLE.REENTER,
                                    LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR,
                                    LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER):
                            unmergableSucNodes.update(loop.iterChannelIoOutsideOfLoop())
                        else:
                            assert role == LOOP_CHANEL_GROUP_ROLE.ENTER
                            #unmergableSucNodes.update(_iterAllChannelIoInsideOfLoop(loop))
            
            elif isinstance(n, HlsNetNodeReadForwardedge):
                unmergablePredNodes.add(n.associatedWrite)
                unmergableSucNodes.add(n.associatedWrite)
                g = n.associatedWrite._loopChannelGroup
                if g is not None:
                    g: LoopChanelGroup
                    for loop, role in g.connectedLoops:
                        assert role not in (LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER,
                                            LOOP_CHANEL_GROUP_ROLE.REENTER), (loop, n, "must always be backedges")
                        if role == LOOP_CHANEL_GROUP_ROLE.ENTER:
                            unmergableSucNodes.update(loop.iterChannelIoOutsideOfLoop())
                        else:
                            assert role == LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR
                            unmergableSucNodes.update(loop.iterChannelIoInsideOfLoop())

            elif isinstance(n, HlsNetNodeWriteForwardedge):
                unmergableSucNodes.add(n.associatedRead)
                g = n._loopChannelGroup
                if g is not None:
                    g: LoopChanelGroup
                    for loop, role in g.connectedLoops:
                        assert role not in (LOOP_CHANEL_GROUP_ROLE.EXIT_NOTIFY_TO_HEADER,
                                            LOOP_CHANEL_GROUP_ROLE.REENTER), (loop, n, "must always be backedges")
                        if role == LOOP_CHANEL_GROUP_ROLE.ENTER:
                            unmergableSucNodes.update(loop.iterChannelIoInsideOfLoop())
                        else:
                            assert role == LOOP_CHANEL_GROUP_ROLE.EXIT_TO_SUCCESSOR
                            unmergableSucNodes.update(loop.iterChannelIoOutsideOfLoop())

        return unmergablePredNodes, unmergableSucNodes

    def update(self, isl):
        # collect sets of islands which can not be merged with this island because of loop control
        if not self.hasNodesWhichTakeTime:
            for n in isl.nodes:
                if isinstance(n, (HlsNetNodeIoClusterCore, HlsNetNodeConst)):
                    pass
                elif isinstance(n, HlsNetNodeOperator) and n.operator in (HwtOps.INDEX, HwtOps.CONCAT):
                    pass
                elif isinstance(n, (HlsNetNodeLoopStatus, HlsProgramStarter,
                                    HlsNetNodeReadForwardedge, HlsNetNodeWriteForwardedge,
                                    HlsNetNodeReadBackedge, HlsNetNodeWriteBackedge)):
                    pass
                else:
                    self.hasNodesWhichTakeTime = True
                    break

        self.unmergableNodes = self._getUnmergableNodes(isl)
        self.isAllNonBlocking = all(isinstance(i, (HlsNetNodeRead, HlsNetNodeWrite)) and not i._isBlocking
                                    for i in isl.inputs)
        self.hasNoIo = not isl.inputs and not isl.outputs


class HlsNetlistPassBetweenSyncIslandsMerge(HlsNetlistPass):
    """
    Iter all islands and merge all trivial cases to predecessor or successor island.
    """

    def __init__(self, dbgTracer: DebugTracer):
        super(HlsNetlistPassBetweenSyncIslandsMerge, self).__init__()
        self._dbgTracer = dbgTracer

    def _islandContainsUnmergable(self, isl: BetweenSyncIsland, unmergableNodes: Set[HlsNetNode]):
        for n in unmergableNodes:
            if n in isl.inputs or \
                    n in isl.outputs or\
                    n in isl.nodes:
                return True
        return False

    def _mayMergeIslands(self, predIsl: BetweenSyncIsland, sucIsl: BetweenSyncIsland,
                         predUnmergableNodes: Optional[Tuple[Set[HlsNetNode], Set[HlsNetNode]]],
                         sucUnmergableNodes: Optional[Tuple[Set[HlsNetNode], Set[HlsNetNode]]]):
        if predUnmergableNodes is not None:
            if self._islandContainsUnmergable(sucIsl, predUnmergableNodes[1]):
                return False

        _sucUnmergableNodes = sucUnmergableNodes
        if sucUnmergableNodes is None:
            sucUnmergableNodes = SyncIslandProps._getUnmergableNodes(sucIsl)

        if self._islandContainsUnmergable(predIsl, sucUnmergableNodes[0]):
            return False

        if predUnmergableNodes is None:
            # :note: the case with predUnmergableNodes is None is also at the beginning
            #  there we compute predUnmergableNodes on demand
            predUnmergableNodes = SyncIslandProps._getUnmergableNodes(predIsl)
            if self._islandContainsUnmergable(sucIsl, predUnmergableNodes[1]):
                return False

        return True

    def _mergeIslands(self, srcIsl: BetweenSyncIsland, dstIsl: BetweenSyncIsland, removedIslands: Set[BetweenSyncIsland]):
        """
        Transfer all nodes from srcIsl to dstIsl update syncIslandOfNode dict and remove srcIsl.

        :attention: dstIsl must not be successor of srcIsl (may be predecessor or parallel to)
        """
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

    def _collectConnectedIslands(self, isl: BetweenSyncIsland) -> Tuple[SetList[BetweenSyncIsland], SetList[BetweenSyncIsland]]:
        syncIslandOfNode = self.syncIslandOfNode
        predIslands: SetList[BetweenSyncIsland] = SetList()
        sucIslands: SetList[BetweenSyncIsland] = SetList()
        for n in chain(isl.inputs, isl.nodes, isl.outputs):
            # no need to check exclude void links as there is no IO and thus void links
            # there are representing data only
            for dep in n.dependsOn:
                if dep._dtype == HVoidOrdering:
                    continue
                predIsl = syncIslandOfNode[dep.obj]
                if isinstance(predIsl, tuple):
                    iIsl, oIsl = predIsl
                    if oIsl is not None:
                        predIslands.append(oIsl)
                    else:
                        assert iIsl is not None, dep.obj
                        predIslands.append(iIsl)
                else:
                    assert predIsl is not None, dep.obj
                    predIslands.append(predIsl)

            for o, uses in zip(n._outputs, n.usedBy):
                if o._dtype == HVoidOrdering:
                    continue

                for u in uses:
                    sucIsl = syncIslandOfNode[u.obj]
                    if isinstance(sucIsl, tuple):
                        iIsl, oIsl = sucIsl
                        # pick island where user node is input
                        if iIsl is not None:
                            sucIslands.append(iIsl)
                        else:
                            assert oIsl is not None, u.obj
                            sucIslands.append(oIsl)
                    else:
                        assert sucIsl is not None, u.obj
                        sucIslands.append(sucIsl)

        predIslands.discard(isl)
        sucIslands.discard(isl)
        return predIslands, sucIslands

    # def checkForwardChannels(self, syncIsland: BetweenSyncIsland):
    #     for io in chain(syncIsland.inputs, syncIsland.outputs):
    #         if isinstance(io, HlsNetNodeReadForwardedge):
    #             w = io.associatedWrite
    #             assert w not in syncIsland.inputs and w not in syncIsland.outputs, (syncIsland, io, w)

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
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
        dbgTracer = self._dbgTracer
        with dbgTracer.scoped(HlsNetlistPassBetweenSyncIslandsMerge, None):
            while True:
                change: bool = False
                for isl in syncIslands:
                    isl: BetweenSyncIsland
                    if isl in removedIslands:
                        continue

                    islProps = SyncIslandProps()  # :note: Not updated if not required after change
                    islProps.update(isl)

                    if islProps.hasNoIo or islProps.isAllNonBlocking or not islProps.hasNodesWhichTakeTime:
                        predIslands, sucIslands = self._collectConnectedIslands(isl)

                        if len(predIslands) == 1 and self._mayMergeIslands(predIslands[0], isl, None, islProps.unmergableNodes):
                            dbgTracer.log(("merge because it is only predecessor", predIslands[0], isl))
                            self._mergeIslands(predIslands[0], isl, removedIslands)
                            change = True

                        elif len(sucIslands) == 1 and self._mayMergeIslands(isl, sucIslands[0], islProps.unmergableNodes, None):
                            dbgTracer.log(("merge because it is only successor", isl, sucIslands[0]))
                            self._mergeIslands(isl, sucIslands[0], removedIslands)
                            change = True
                        elif len(predIslands) == 1 and len(sucIslands) == 1 and predIslands[0] == sucIslands[0] and not islProps.hasNodesWhichTakeTime:
                            dbgTracer.log(("merge zero time control triangle", isl, sucIslands[0]))
                            self._mergeIslands(isl, sucIslands[0], removedIslands)
                        elif len(predIslands) > 1:
                            for predIsl in predIslands:
                                if predIsl in sucIslands and self._mayMergeIslands(predIsl, isl, None, islProps.unmergableNodes):
                                    # if this island depends on some other islad at the begin and at the end
                                    # there is no point in keeping it as a separate thread.
                                    dbgTracer.log(("merge because it there is a cycle", predIsl, isl))
                                    self._mergeIslands(predIsl, isl, removedIslands)
                                    change = True
                                    break

                            if change:
                                continue

                            # merge to some successor or predecessor which is scheduled to the same clock cycle
                            schedTimes = isl.getScheduledClkTimes(clkPeriod)
                            for otherIsl, isPred in chain(((i, True) for i in predIslands),
                                                          ((i, False) for i in sucIslands)):
                                otherSchedTimes = otherIsl.getScheduledClkTimes(clkPeriod)
                                if schedTimes.issubset(otherSchedTimes):
                                    if isPred:
                                        if self._mayMergeIslands(otherIsl, isl, None, islProps.unmergableNodes):
                                            dbgTracer.log(("merge because predecessor scheduled to same time", isl, otherIsl))
                                            self._mergeIslands(otherIsl, isl, removedIslands)
                                            change = True
                                            break
                                    else:
                                        if self._mayMergeIslands(isl, otherIsl, islProps.unmergableNodes, None):
                                            dbgTracer.log(("merge because successor scheduled to same time", otherIsl, isl))
                                            self._mergeIslands(isl, otherIsl, removedIslands)

                                            change = True
                                            break

                    elif islProps.hasNodesWhichTakeTime:
                        if len(isl.inputs) == 1 and not len(isl.outputs):
                            # merge to predecessor because this cluster has just this out node
                            # which is synchronization itself and thus no additional sync is required
                            inp: HlsNetNodeExplicitSync = isl.inputs[0]
                            predCluster = inp.dependsOn[inp._outputOfCluster.in_i].obj
                            predIsl = syncIslandOfNode[predCluster]
                            if predIsl is not isl and self._mayMergeIslands(isl, sucIslands[0], islProps.unmergableNodes, None):
                                dbgTracer.log(("merge trivial island with input", isl, predIsl))
                                self._mergeIslands(isl, predIsl, removedIslands)
                                change = True

                        elif not isl.inputs and len(isl.outputs) == 1:
                            out: HlsNetNodeExplicitSync = isl.outputs[0]
                            sucCluster = out.dependsOn[out._inputOfCluster.in_i].obj
                            sucIsl = syncIslandOfNode[sucCluster]
                            if sucIsl is not isl and self._mayMergeIslands(predIsl, isl, None, islProps.unmergableNodes):
                                dbgTracer.log(("merge trivial island with output", sucIsl, isl))
                                self._mergeIslands(sucIsl, isl, removedIslands)
                                change = True

                if not change:
                    break

        # for n, isl in syncIslandOfNode.items():
        #    assert isl not in removedIslands, (n, isl)
        syncIslands[:] = (i for i in syncIslands if i not in removedIslands)
        #for syncIsland in syncIslands:
        #    self.checkForwardChannels(syncIsland)
        # if cluster contains only HlsNetNodeExplicitSync and optional HlsNetNodeReadSync
        # and has only successor or only predecessor it can be merged into it

        # clusters which do have just 1 predecessor can be merged
        #   1 -> 2 -> 3         1,2 -> 3
        #         |-> 4            |-> 4

        # concurrently executable branches may be merged if they do have same successor and no other predecessor
        #   1 -> 2 --> 4    1 -> 2|3 -> 4
        #    |-> 3 -|
        return PreservedAnalysisSet.preserveAll() # because this just updates HlsNetlistAnalysisPassBetweenSyncIslands
