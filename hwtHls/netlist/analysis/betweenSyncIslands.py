from itertools import chain
from typing import List, Set, Dict, Tuple, Union

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.betweenSyncIslandsUtils import BetweenSyncIsland
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import LoopChanelGroup, \
    LOOP_CHANEL_GROUP_ROLE
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from ipCorePackager.constants import DIRECTION


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

    def __init__(self):
        super(HlsNetlistAnalysisPassBetweenSyncIslands, self).__init__()
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
    def discoverSyncIsland(cls, node: HlsNetNodeExplicitSync, incommingDir: DIRECTION, reachDb: HlsNetlistAnalysisPassReachability)\
            ->Tuple[SetList[HlsNetNodeExplicitSync], SetList[HlsNetNodeExplicitSync]]:
        """
        This function search for sync nodes related to specified input node.
        First search for all users of this node outputs
        and then again checks if there are more other sync dependencies and repeats the search
        while new sync nodes are discovered.

        :note: There may be some nodes which are both input and output.
        """

        # find boundaries of local synchronization cluster
        inputs: SetList[HlsNetNodeExplicitSync] = SetList()
        outputs: SetList[HlsNetNodeExplicitSync] = SetList()
        toSearchDefToUse: List[HlsNetNode] = []
        toSearchUseToDef: List[HlsNetNode] = []
        seenDefToUse: Set[HlsNetNode] = set()
        seenUseToDef: Set[HlsNetNode] = set()
        internalNodes: SetList[HlsNetNode] = SetList()

        if incommingDir == DIRECTION.IN:
            toSearchDefToUse.append(node)
            inputs.append(node)
        else:
            assert incommingDir == DIRECTION.OUT, incommingDir
            toSearchUseToDef.append(node)
            outputs.append(node)

        while toSearchUseToDef or toSearchDefToUse:

            for n in reachDb._getDirectDataSuccessorsRaw(toSearchDefToUse, set()):
                assert not isinstance(n, HlsNetNodeAggregate), n
                # search def <- use  (top <- down)
                if n not in seenUseToDef:
                    seenUseToDef.add(n)
                    toSearchUseToDef.append(n)

                if isinstance(n, HlsNetNodeExplicitSync):
                    outputs.append(n)
                else:
                    internalNodes.append(n)

            for n in reachDb._getDirectDataPredecessorsRaw(toSearchUseToDef, set()):
                assert isinstance(n, HlsNetNode), n
                assert not isinstance(n, HlsNetNodeAggregate), n
                # search def -> use (top -> down)
                if n not in seenDefToUse:
                    seenDefToUse.add(n)
                    toSearchDefToUse.append(n)

                # io of the loop must be in the same node as HlsNetNodeLoopStatus,
                # for each io add also HlsNetNodeLoopStatus
                if isinstance(n, HlsNetNodeExplicitSync):
                    inputs.append(n)
                    if isinstance(n, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)):
                        chGroup = n.associatedWrite._loopChannelGroup
                        if chGroup is not None and chGroup.getChannelUsedAsControl() is n:
                            chGroup: LoopChanelGroup
                            for loop, role in chGroup.connectedLoopsAndBlocks:
                                if role not in (
                                    LOOP_CHANEL_GROUP_ROLE.ENTER,
                                    LOOP_CHANEL_GROUP_ROLE.REENTER,
                                    ):
                                    continue
                                elif loop not in seenDefToUse and loop not in internalNodes:
                                    seenDefToUse.add(loop)
                                    toSearchDefToUse.append(loop)
                else:
                    nIsNewlyAdded = internalNodes.append(n)
                    if nIsNewlyAdded and isinstance(n, HlsNetNodeLoopStatus):
                        n: HlsNetNodeLoopStatus
                        for chGroup in n.iterConnectedInputChannelGroups():
                            chGroup: LoopChanelGroup
                            if chGroup.getRoleForLoop(n) not in (
                                LOOP_CHANEL_GROUP_ROLE.ENTER,
                                LOOP_CHANEL_GROUP_ROLE.REENTER,
                                ):
                                continue
                            w = chGroup.getChannelUsedAsControl()
                            r = w.associatedRead
                            if r not in seenDefToUse:
                                inputs.append(r)
                                seenDefToUse.add(r)
                                toSearchDefToUse.append(r)

        # inputs may dependent on outputs because we stop search
        # after first found HlsNetNodeExplicitSync instance
        iOffset = 0
        _inputs = tuple(inputs)
        for ii, i in enumerate(_inputs):
            for o in chain(outputs, _inputs):
                if reachDb.doesReachToData(o, i):
                    _i = inputs.pop(iOffset + ii)
                    assert _i is i
                    outputs.append(i)
                    iOffset -= 1
                    break

        return inputs, outputs, internalNodes

    def _collectSyncIslandByFlooding(self, reachDb: HlsNetlistAnalysisPassReachability, n: HlsNetNodeIoClusterCore):
        syncIslandOfNode = self.syncIslandOfNode

        _inputs = n.usedBy[n.inputNodePort.out_i]
        _outputs = n.usedBy[n.outputNodePort.out_i]

        if _inputs:
            n0 = _inputs[0].obj
            d = DIRECTION.IN
        else:
            n0 = _outputs[0].obj
            d = DIRECTION.OUT

        inputs, outputs, nodes = self.discoverSyncIsland(n0, d, reachDb)
        for io in chain(inputs, outputs):
            io: HlsNetNodeExplicitSync
            # :attention: input does not necessary be connected to _inputOfCluster but may be connected to _outputOfCluster
            #   that is because original cluster takes void connections in account while now void connections are ignored
            #   thus outputs may become inputs if
            iClus: HlsNetNodeIoClusterCore = io.dependsOn[io._inputOfCluster.in_i].obj
            oClus: HlsNetNodeIoClusterCore = io.dependsOn[io._outputOfCluster.in_i].obj
            if iClus is n:
                ioDir = DIRECTION.IN
                neighborClus = oClus
            else:
                assert oClus is n
                ioDir = DIRECTION.OUT
                neighborClus = iClus

            if sum(len(uses) for uses in neighborClus.usedBy) == 1:
                assert neighborClus not in syncIslandOfNode.keys(), (neighborClus, io)
                _inputs, _outputs, _nodes = self.discoverSyncIsland(io, DIRECTION.opposite(ioDir), reachDb)
                nodes.append(neighborClus)
                nodes.extend(_nodes)

        nodes.append(n)
        island = BetweenSyncIsland(inputs, outputs, nodes)
        self._addNodesFromIslandToSyncIslandOfNodeDict(island)
        self.syncIslands.append(island)

    def _collectSyncIslandsByFlooding(self, netlist:"HlsNetlistCtx", reachDb: HlsNetlistAnalysisPassReachability):
        syncIslandOfNode = self.syncIslandOfNode

        # singleIoClusters: List[HlsNetNodeIoClusterCore] = []
        for ioClusterNode in netlist.iterAllNodes():
            if ioClusterNode not in syncIslandOfNode.keys() and isinstance(ioClusterNode, HlsNetNodeIoClusterCore):
                ioClusterNode: HlsNetNodeIoClusterCore
                _inputs = ioClusterNode.usedBy[ioClusterNode.inputNodePort.out_i]
                _outputs = ioClusterNode.usedBy[ioClusterNode.outputNodePort.out_i]
                if len(_inputs) + len(_outputs) == 1:
                    if _inputs:
                        # search predecessor cluster and this will be added automatically
                        boundaryIoNode = _inputs[0].obj
                    else:
                        # search successor cluster and this will be added automatically
                        boundaryIoNode = _outputs[0].obj

                    iClus = boundaryIoNode.dependsOn[boundaryIoNode._inputOfCluster.in_i].obj
                    oClus = boundaryIoNode.dependsOn[boundaryIoNode._outputOfCluster.in_i].obj
                    if iClus is ioClusterNode:
                        assert oClus is not ioClusterNode
                        assert oClus not in syncIslandOfNode.keys(), (
                            "If any connected cluster core was already seen, this should be seen as well",
                            ioClusterNode, oClus, boundaryIoNode)
                        clusNode = oClus
                    else:
                        assert oClus is ioClusterNode, (
                            "Check that the ioClusterNode is output of boundaryIoNode if it was not input",
                            boundaryIoNode, ioClusterNode, oClus)
                        assert iClus is not ioClusterNode
                        assert iClus not in syncIslandOfNode.keys(), (
                            "If any connected cluster core was already seen, this should be seen as well",
                            ioClusterNode, iClus, boundaryIoNode)
                        clusNode = iClus
                else:
                    clusNode = ioClusterNode

                self._collectSyncIslandByFlooding(reachDb, clusNode)

    def _collectDirectyConnectedConstNodesWithoutIslandUseToDef(self, node: HlsNetNode):
        for dep in node.dependsOn:
            depO = dep.obj
            if depO not in self.syncIslandOfNode and isinstance(depO, HlsNetNodeConst):
                yield depO

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
        internalNodes: SetList[HlsNetNode] = SetList((node,))

        if incommingDir == DIRECTION.IN:
            toSearchDefToUse.append(node)
        elif incommingDir == DIRECTION.OUT:
            toSearchUseToDef.append(node)
            internalNodes.extend(self._collectDirectyConnectedConstNodesWithoutIslandUseToDef(node))
        else:
            assert incommingDir == DIRECTION.INOUT, incommingDir
            toSearchDefToUse.append(node)
            toSearchUseToDef.append(node)

        resolvedNodes = syncIslandOfNode.keys()
        while toSearchUseToDef or toSearchDefToUse:
            for n in HlsNetlistAnalysisPassReachability._getDirectDataSuccessorsRawAnyData(toSearchDefToUse, seenDefToUse, resolvedNodes.__contains__):
                # search use -> def (top -> down)
                internalNodes.extend(self._collectDirectyConnectedConstNodesWithoutIslandUseToDef(n))
                if n not in seenUseToDef:
                    toSearchUseToDef.append(n)
                internalNodes.append(n)

            for n in HlsNetlistAnalysisPassReachability._getDirectDataPredecessorsRawAnyData(toSearchUseToDef, seenUseToDef, resolvedNodes.__contains__):
                # search use -> def (top -> down)
                internalNodes.extend(self._collectDirectyConnectedConstNodesWithoutIslandUseToDef(n))
                if n not in seenDefToUse:
                    toSearchDefToUse.append(n)
                internalNodes.append(n)

        return internalNodes

    def _collectLeftOutNodesToOwnIslandsOrMergeIfPossible(self):
        syncIslands = self.syncIslands
        syncIslandOfNode = self.syncIslandOfNode
        # search for node groups without island before this island
        for isl in syncIslands:
            isl: BetweenSyncIsland
            for n in isl.iterAllNodes():
                n: HlsNetNode
                for dep in n.dependsOn:
                    depO = dep.obj
                    depOIsl = syncIslandOfNode.get(depO, None)
                    if depOIsl is None:
                        nodes = self._collectNodesWithoutIsland(depO, DIRECTION.INOUT)
                        isl = BetweenSyncIsland(SetList(), SetList(), nodes)
                        syncIslands.append(isl)
                        for n0 in isl.nodes:
                            syncIslandOfNode[n0] = isl

        # search for node groups without island after this island
        for isl in syncIslands:
            isl: BetweenSyncIsland
            for n in isl.iterAllNodes():
                n: HlsNetNode
                for uses in n.usedBy:
                    for u in uses:
                        useO = u.obj
                        useOIsl = syncIslandOfNode.get(useO, None)
                        if useOIsl is None:
                            nodes = self._collectNodesWithoutIsland(useO, DIRECTION.INOUT)
                            isl = BetweenSyncIsland(SetList(), SetList(), nodes)
                            syncIslands.append(isl)
                            for n0 in isl.nodes:
                                syncIslandOfNode[n0] = isl

        # syncIslandOfNode = self.syncIslandOfNode
        #    syncDomains = netlist.getAnalysis(HlsNetlistAnalysisPassSyncDomains)
        #    for n in netlist.iterAllNodes():
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

    @override
    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        """
        Discover clusters of nodes which are definitely a consecutive cluster with HlsNetNodeExplicitSync nodes on its boundaries.
        """
        reachDb = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)
        self._collectSyncIslandsByFlooding(netlist, reachDb)
        seen = self.syncIslandOfNode
        if len(seen) != len(netlist.inputs) + len(netlist.nodes) + len(netlist.outputs):
            self._collectLeftOutNodesToOwnIslandsOrMergeIfPossible()

