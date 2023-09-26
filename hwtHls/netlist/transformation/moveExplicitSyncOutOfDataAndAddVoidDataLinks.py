from typing import List, Tuple

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.orderable import HVoidData
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes, \
    link_hls_nodes
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass


class HlsNetlistPassMoveExplicitSyncOutOfDataAndAddVoidDataLinks(HlsNetlistPass):
    """
    The HlsNetNodeExplicitSync instances are removed from connections with of regular datatypes and
    are placed on newly created connections of HVoidData type.
    
    :note: This is beneficial mainly because it puts sync information out of dense data expression
        graph. Search for sync pattens is faster and it is not necessary to check many positions
        when hoisting.
    """

    def apply(self, hls:"HlsScope", netlist:HlsNetlistCtx):
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
                    preds = tuple(n0 for n0 in HlsNetlistAnalysisPassReachability._getDirectDataPredecessorsRaw(UniqList((srcObj,)), set())
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
                preds = tuple(n0 for n0 in HlsNetlistAnalysisPassReachability._getDirectDataPredecessorsRaw(UniqList((n,)), set())
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
