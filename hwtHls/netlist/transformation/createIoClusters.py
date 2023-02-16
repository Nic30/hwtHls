from typing import Tuple, List

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.orderable import HVoidData
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes, unlink_hls_nodes
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from ipCorePackager.constants import DIRECTION


class HlsNetlistPassCreateIoClusters(HlsNetlistPass):
    """
    Discover all HlsNetNodeExplicitSync node relations and extract HlsNetNodeIoClusterCore nodes which are conecting
    tied HlsNetNodeExplicitSync instances.
    To guarantee that the ordering remains the same after circuit optimization. 
    """

    @staticmethod
    def createIoClusterCore(netlist:HlsNetlistCtx, inputs: UniqList[HlsNetNodeExplicitSync], outputs:UniqList[HlsNetNodeExplicitSync]) -> HlsNetNodeIoClusterCore:
        # print("createIoClusterCore", [i._id for i in inputs], [o._id for o in outputs])
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

        return cc

    def moveExplicitSyncOutOfDataAndAddVoidDataLinks(self, hls:"HlsScope", netlist:HlsNetlistCtx):
        """
        The HlsNetNodeExplicitSync instances are removed from connections with of regular datatypes and
        are placed on newly created connections of HVoidData type.
    
        :note: This is benificial mainly because it puts sync information out of dense data expression
            graph. Search for sync pattens is faster and it is not necessary to check many positions
            when hoisting.
        """

        b: HlsNetlistBuilder = netlist.builder
        syncNodes: List[Tuple[HlsNetNodeExplicitSync, HlsNetNodeOut]] = []
        for n in netlist.iterAllNodes():
            if n.__class__ is HlsNetNodeExplicitSync:
                if n._outputs[0]._dtype == HVoidData:
                    # was already converted
                    continue
                # reconnect inputs of HlsNetNodeExplicitSync nodes to VoidData
                dataSrc = n.dependsOn[0]
                srcObj = dataSrc.obj
                if isinstance(srcObj, HlsNetNodeExplicitSync):
                    preds = (srcObj,)
                else:
                    preds = tuple(n0 for n0 in HlsNetlistAnalysisPassReachabilility._getDirectDataPredecessorsRaw(UniqList((srcObj,)), set())
                                  if isinstance(n0, HlsNetNodeExplicitSync))
                unlink_hls_nodes(dataSrc, n._inputs[0])
                predOOuts = tuple(pred.getDataVoidOutPort() for pred in preds)
                if predOOuts:
                    orderingSrc = b.buildConcatVariadic(predOOuts)
                else:
                    orderingSrc = b.buildConst(HVoidData.from_py(None))

                link_hls_nodes(orderingSrc, n._inputs[0])
                # store to temporarly list because we can not modify during analysis
                syncNodes.append((n, dataSrc))

            elif isinstance(n, HlsNetNodeExplicitSync):
                # case for HLsNetNodeRead/Wrtite and alike
                preds = tuple(n0 for n0 in HlsNetlistAnalysisPassReachabilility._getDirectDataPredecessorsRaw(UniqList((n,)), set())
                                  if isinstance(n0, HlsNetNodeExplicitSync))
                # add explicit data void conection to predecessor if it does not exist
                # because later during optimizations current data link may be lost
                for pred in preds:
                    nOi = n._addInput("dataOrderingIn")
                    link_hls_nodes(pred.getDataVoidOutPort() , nOi)

        for n, dataSrc in syncNodes:
            # finalize disconnect sync from data, (inputs are updated, now finishing )
            n: HlsNetNodeExplicitSync
            b.replaceOutput(n._outputs[0], dataSrc, True)
            n._outputs[0]._dtype = HVoidData
            if n._dataVoidOut:
                b.replaceOutput(n._dataVoidOut, n._outputs[0], True)
                n._removeOutput(n._dataVoidOut.out_i)

    def createIoClusterCores(self, netlist: HlsNetlistCtx, reachDb: HlsNetlistAnalysisPassReachabilility):
        allSync = []
        for n in netlist.iterAllNodes():
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
            self.moveExplicitSyncOutOfDataAndAddVoidDataLinks(hls, netlist) 
            reachDb = netlist.getAnalysis(HlsNetlistAnalysisPassReachabilility)
            self.createIoClusterCores(netlist, reachDb)
                  
        finally:
            netlist.invalidateAnalysis(HlsNetlistAnalysisPassReachabilility)

