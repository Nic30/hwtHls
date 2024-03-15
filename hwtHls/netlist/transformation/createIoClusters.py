from itertools import chain

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import link_hls_nodes
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from ipCorePackager.constants import DIRECTION


class HlsNetlistPassCreateIoClusters(HlsNetlistPass):
    """
    Discover all HlsNetNodeExplicitSync node relations and extract HlsNetNodeIoClusterCore nodes which are conecting
    tied HlsNetNodeExplicitSync instances.
    To guarantee that the ordering remains the same after circuit optimization.

    :attention: Expects HlsNetlistPassMoveExplicitSyncOutOfDataAndAddVoidDataLinks to be applied before.
    """

    @staticmethod
    def createIoClusterCore(netlist:HlsNetlistCtx,
                            inputs: UniqList[HlsNetNodeExplicitSync],
                            outputs:UniqList[HlsNetNodeExplicitSync]) -> HlsNetNodeIoClusterCore:
        assert inputs or outputs
        cc = HlsNetNodeIoClusterCore(netlist)
        netlist.nodes.append(cc)
        iPort = cc.inputNodePort
        for i in inputs:
            i: HlsNetNodeExplicitSync
            link_hls_nodes(iPort, i.getInputOfClusterPort())

        if outputs:
            oPort = cc.outputNodePort
            for o in outputs:
                o: HlsNetNodeExplicitSync
                link_hls_nodes(oPort, o.getOutputOfClusterPort())

        minT = None
        for io in chain(inputs, outputs):
            io: HlsNetNodeExplicitSync
            if io.scheduledZero is None:
                # this was called on not scheduled netlist, we skip resolution of schedulation time
                assert minT is None, (io, inputs, outputs)
                return cc
            elif minT is None:
                minT = io.scheduledZero
            else:
                minT = min(minT, io.scheduledZero)

        assert minT is not None
        cc.setScheduling({cc: (minT, tuple(minT for _ in cc._inputs), tuple(minT for _ in cc._outputs))})

        return cc

    def createIoClusterCores(self, netlist: HlsNetlistCtx, reachDb: HlsNetlistAnalysisPassReachability):
        assert not netlist.builder._removedNodes
        allSync = []
        for n in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.OMMIT_PARENT):
            if isinstance(n, HlsNetNodeExplicitSync):
                # to have outputOfClusterPort before input
                # (because data flows from up to down visualization graphs and this port order improves readability)
                n.getOutputOfClusterPort()
                n.getInputOfClusterPort()
                allSync.append(n)

        for n in allSync:
            n: HlsNetNodeExplicitSync
            if n.dependsOn[n._inputOfCluster.in_i] is None:
                inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(n, DIRECTION.IN, reachDb)
                inputs = UniqList((i for i in inputs if i not in outputs))
                if n in inputs or n.dependsOn[n._outputOfCluster.in_i] is None:
                    self.createIoClusterCore(netlist, inputs, outputs)

            if n.dependsOn[n._outputOfCluster.in_i] is None:
                inputs, outputs, _ = HlsNetlistAnalysisPassBetweenSyncIslands.discoverSyncIsland(n, DIRECTION.OUT, reachDb)
                inputs = UniqList((i for i in inputs if i not in outputs))

                self.createIoClusterCore(netlist, inputs, outputs)
                assert n.dependsOn[n._outputOfCluster.in_i] is not None, n

        for n in allSync:
            if n.dependsOn[n._inputOfCluster.in_i] is None:
                self.createIoClusterCore(netlist, UniqList((n,)), UniqList())

    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx):
        try:
            reachDb = netlist.getAnalysis(HlsNetlistAnalysisPassReachability)
            self.createIoClusterCores(netlist, reachDb)
        finally:
            netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachability)

