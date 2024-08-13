from typing import Set, List

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.detectFsms import HlsNetlistAnalysisPassDetectFsms, \
    IoFsm
from hwtHls.netlist.analysis.detectPipelines import HlsNetlistAnalysisPassDetectPipelines, \
    NetlistPipeline
from hwtHls.netlist.clusterSearch import HlsNetlistClusterSearch
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsNetlistPassAggregateArchElements(HlsNetlistPass):
    """
    Query HlsNetlistAnalysisPassDiscoverFsm and HlsNetlistAnalysisPassDiscoverPipelines
    to search ArchElement instances in current HlsNetlist.

    The process of architecture generation is based on discovery of resources which do require arbitration and on discovery
    parallel/asynchronous segments of netlist. For this purpose there are several objects are used:
      * HlsNetNodeIoClusterCore - A netlist node which is used during optimization of the netlist to keep information
          about every IO which needs to be taken in account when optimizing IO access conditions.
      * HlsNetlistAnalysisPassSyncDomains - A pass which discovers the parts of IO cluster which must happen atomically and
          which are subject to some kind of combinational loop later in architecture generation.
      * HlsNetlistAnalysisPassBetweenSyncIslands - A pass which discovers nodes in the body of the IO cluster. Produces BetweenSyncIsland.
    
    * An information form previously mentioned objects is then used to construct :class:`hwtHls.netlist.nodes.archElement.ArchElement` instances.
    
    https://math.stackexchange.com/questions/3836719/dag-decomposition-into-parallel-components
    https://en.wikipedia.org/wiki/Series%E2%80%93parallel_graph
    https://en.wikipedia.org/wiki/SPQR_tree

    :ivar _dbgAddSignalNamesToSync: add names to synchronization signals in order to improve readability
    """

    def __init__(self, dbgAddNamesToSyncSignals: bool):
        HlsNetlistPass.__init__(self)
        self._dbgAddSignalNamesToSync = dbgAddNamesToSyncSignals

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        """
        Query HlsNetlistAnalysisPassDiscoverFsm and HlsNetlistAnalysisPassDiscoverPipelines to search ArchElement instances
        in current HlsNetlist.
        """
        namePrefix: str = netlist.namePrefix
        fsms: HlsNetlistAnalysisPassDetectFsms = netlist.getAnalysis(HlsNetlistAnalysisPassDetectFsms)
        pipelines: HlsNetlistAnalysisPassDetectPipelines = netlist.getAnalysis(HlsNetlistAnalysisPassDetectPipelines)
        onlySingleElem = (len(fsms.fsms) + len(pipelines.pipelines)) == 1
        archElements: List[ArchElement] = []
        removedNodes: Set[HlsNetNode] = set()
        for i, ioFsm in enumerate(fsms.fsms):
            ioFsm: IoFsm
            allNodes: SetList[HlsNetNode] = SetList()
            for nodes in ioFsm.states:
                allNodes.extend(nodes)
                for n in nodes:
                    assert n not in removedNodes, n
                    assert not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)), n

            c: HlsNetlistClusterSearch = HlsNetlistClusterSearch.discoverFromNodeList(allNodes)
            name: str = namePrefix if onlySingleElem else f"{namePrefix:s}fsm{i:d}_"
            fsmClusterNode = ArchElementFsm(netlist, name, c.nodes, ioFsm)
            c.substituteWithNode(fsmClusterNode, requiredToBeScheduled=True)
            fsmClusterNode.checkScheduling()
            archElements.append(fsmClusterNode)
            removedNodes.update(c.nodes)

        for i, pipe in enumerate(pipelines.pipelines):
            pipe: NetlistPipeline
            allNodes = SetList()
            for nodes in pipe.stages:
                allNodes.extend(nodes)
                for n in nodes:
                    assert n not in removedNodes, n
                    assert not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)), n

            c: HlsNetlistClusterSearch = HlsNetlistClusterSearch.discoverFromNodeList(allNodes)
            name: str = namePrefix if onlySingleElem else f"{namePrefix:s}pipe{i:d}_"
            pipeClusterNode = ArchElementPipeline(netlist, name,
                                           allNodes, pipe.stages, pipe.syncIsland)
            c.substituteWithNode(pipeClusterNode, requiredToBeScheduled=True)
            pipeClusterNode.checkScheduling()

            archElements.append(pipeClusterNode)
            removedNodes.update(c.nodes)

        for elm in archElements:
            elm._dbgAddSignalNamesToSync = self._dbgAddSignalNamesToSync

        netlistNodeContainers = (netlist.inputs, netlist.outputs, netlist.nodes)
        leftOverNodes = set()
        for cont in netlistNodeContainers:
            leftOverNodes.update(cont)
        leftOverNodes = leftOverNodes.difference(removedNodes)

        if leftOverNodes:
            raise AssertionError(
            "Each node should be in pipeline or FSM there should be nothing left",
            sorted(leftOverNodes, key=lambda n: n._id),
            )

        for container in netlistNodeContainers:
            container.clear()

        netlist.filterNodesUsingSet(removedNodes)
        # drop builder.operatorCache because we removed most of bitwise operator from the circuit
        netlist.builder.operatorCache.clear()
        netlist.nodes.extend(archElements)
        return PreservedAnalysisSet.preserveSchedulingOnly()

