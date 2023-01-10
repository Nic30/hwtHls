from typing import Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.syncDependecy import HlsNetlistAnalysisPassSyncDependency
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import unlink_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer


def netlistBackedgeStraightening(dbgTracer: DebugTracer,
                                 w: HlsNetNodeWriteBackwardEdge,
                                 worklist: UniqList[HlsNetNode],
                                 removed: Set[HlsNetNode],
                                 syncDeps: HlsNetlistAnalysisPassSyncDependency):
    # r is ordered before w because this is backedge
    # if w does not depend on r and none of them 
    
    r = w.associated_read
    if r is None:
        return False

    if w.channel_init_values:
        return False
    
    rValidPortReplacement = None
    rValidNBPortReplacement = None 
    hasUsedValidNBPort = r.hasValidNB() and r.usedBy[r._validNB.out_i]
    hasUsedValidPort = r.hasValid() and r.usedBy[r._valid.out_i]
    if hasUsedValidNBPort or hasUsedValidPort:
        dataPredecs = syncDeps.getDirectDataPredecessors(w._inputs[0])
        if hasUsedValidPort:
            if len(dataPredecs) == 1 and isinstance(dataPredecs[0], HlsNetNodeRead):
                rValidPortReplacement = dataPredecs[0].getValid()
            else:
                return False
        
        if hasUsedValidNBPort:
            if len(dataPredecs) == 1 and isinstance(dataPredecs[0], HlsNetNodeRead):
                rValidNBPortReplacement = dataPredecs[0].getValidNB()
            else:
                return False

    if r.extraCond is not None or r.skipWhen is not None:
        return False

    if w.extraCond is not None or w.extraCond is not None:
        return False

    if syncDeps.doesReachTo(r, w):
        # if write is dependent on read the channel can not be removed
        # because state of the channel state can is required 
        return False
    
    with dbgTracer.scoped(netlistBackedgeStraightening, w):
        orderingDeps = []
        orderingUses = []
        for n in (r, w):
            for i in n.iterOrderingInputs():
                dep = n.dependsOn[i.in_i]
                if i.obj not in (r, w):
                    orderingDeps.append(dep)
                unlink_hls_nodes(dep, i)
            oo = n.getOrderingOutPort()
            for u in n.usedBy[oo.out_i]:
                if u.obj not in (r, w):
                    orderingUses.append(u)
                unlink_hls_nodes(oo, u)
        
        if orderingDeps or orderingUses:
            # delegate ordering to successor
            raise NotImplementedError(w)
        # replace this read-write pair with a straight connection
        data = w.dependsOn[0]
        unlink_hls_nodes(data, w._inputs[0])
        rData = r._outputs[0]
        b: HlsNetlistBuilder = r.netlist.builder
        dbgTracer.log(("replace", rData, data))
        b.replaceOutput(rData, data, True)
        
        if rValidPortReplacement is not None:
            b.replaceOutput(r._valid, rValidPortReplacement, True)
        if rValidNBPortReplacement is not None:
            b.replaceOutput(r._validNB, rValidNBPortReplacement, True)
        
        removed.add(r)
        removed.add(w)
        return True
