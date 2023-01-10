from typing import List, Optional, Set, Tuple

from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.orderable import HOrderingVoidT, HdlType_isNonData
from hwtHls.netlist.nodes.ports import link_hls_nodes, unlink_hls_nodes, \
    HlsNetNodeOut
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.simplifySync.simplifySyncUtils import netlistContainsExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.transformation.simplifySync.simplifyOrdering import _explicitSyncAddUniqueOrdering
from hwt.pyUtils.uniqList import UniqList


class HlsNetlistPassExplicitSyncDataToOrdering(HlsNetlistPass):
    """
    Transplant HlsNetNodeExplicitSync instances from data channels to ordering channels.
    """

    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx, parentRemoved: Optional[Set[HlsNetNode]]=None):
        if not netlistContainsExplicitSync(netlist, None):
            return
        b: HlsNetlistBuilder = netlist.builder
        try:
            syncNodes: List[Tuple[HlsNetNodeExplicitSync, HlsNetNodeOut]] = []
            for n in netlist.iterAllNodes():
                if parentRemoved is not None and n in parentRemoved:
                    continue
                if n.__class__ is HlsNetNodeExplicitSync:
                    if n._outputs[0]._dtype == HOrderingVoidT:
                        continue
                    # reconnect inputs of HlsNetNodeExplicitSync nodes to ordering
                    preds = tuple(HlsNetlistAnalysisPassSyncDependency.getDirectDataPredecessors(n._inputs[0]))
                    dataSrc = n.dependsOn[0]
                    unlink_hls_nodes(n.dependsOn[0], n._inputs[0])
                    predOOuts = tuple(pred.getOrderingOutPort() for pred in preds)
                    if predOOuts:
                        orderingSrc = b.buildConcatVariadic(predOOuts)
                    else:
                        orderingSrc = b.buildConst(HOrderingVoidT.from_py(None))

                    link_hls_nodes(orderingSrc, n._inputs[0])
                    syncNodes.append((n, dataSrc))

                elif isinstance(n, HlsNetNodeExplicitSync):
                    preds = UniqList()
                    for i in n._inputs:
                        if i is n.extraCond or i is n.skipWhen:
                            continue
                        dep = n.dependsOn[i.in_i]
                        if dep is None or HdlType_isNonData(dep._dtype):
                            continue
                        preds.extend(HlsNetlistAnalysisPassSyncDependency.getDirectDataPredecessors(dep))

                    _explicitSyncAddUniqueOrdering(n, (pred.getOrderingOutPort() for pred in preds), None)
                    
            for n, dataSrc in syncNodes:
                # finalize disconnect sync from data
                b.replaceOutput(n._outputs[0], dataSrc, True)
                n._outputs[0]._dtype = HOrderingVoidT

        finally:
            netlist.dropNetlistListeners()
