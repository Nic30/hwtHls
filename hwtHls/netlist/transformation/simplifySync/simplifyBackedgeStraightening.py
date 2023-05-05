from typing import Set, List

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachabilility
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import unlink_hls_nodes, HlsNetNodeOut, \
    HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.orderable import HVoidData, HVoidExternData
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist


def netlistBackedgeStraightening(dbgTracer: DebugTracer,
                                 w: HlsNetNodeWriteBackedge,
                                 worklist: UniqList[HlsNetNode],
                                 removed: Set[HlsNetNode],
                                 reachDb: HlsNetlistAnalysisPassReachabilility):
    """
    Move if write to backedge channel before read it possible and optionally remove
    the chanel and read+write entirely.
    """
    # r is ordered before w because this is backedge
    # if w does not depend on r and none of them 
    
    r = w.associatedRead
    if r is None:
        return False

    if w.channelInitValues:
        return False
    
    rValidPortReplacement = None
    rValidNBPortReplacement = None 
    hasUsedValidNBPort = r.hasValidNB() and r.usedBy[r._validNB.out_i]
    hasUsedValidPort = r.hasValid() and r.usedBy[r._valid.out_i]
    if hasUsedValidNBPort or hasUsedValidPort:
        dataPredecs = reachDb.getDirectDataPredecessors(w)
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

    if reachDb.doesReachTo(r, w):  # [todo] ignore ordering and void data
        # if write is dependent on read the channel can not be removed
        # because state of the channel state can is required 
        return False
    
    with dbgTracer.scoped(netlistBackedgeStraightening, w):
        orderingDeps: List[HlsNetNodeOut] = []
        orderingUses: List[HlsNetNodeIn] = []
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
            if len(orderingDeps) + len(orderingUses) > 1:
                # delegate ordering to successor
                raise NotImplementedError(w)
            else:
                for u in orderingUses:
                    u.obj._removeInput(u.in_i)

        # replace this read-write pair with a straight connection
        data = w.dependsOn[0]
        unlink_hls_nodes(data, w._inputs[0])
        rData = r._outputs[0]
        b: HlsNetlistBuilder = r.netlist.builder
        dbgTracer.log(("replace", rData, data))
        b.replaceOutput(rData, data, True)
        addAllUsersToWorklist(worklist, r)
        addAllUsersToWorklist(worklist, w)

        if r._dataVoidOut is not None:
            if orderingDeps:
                raise NotImplementedError("Construct a dataVoidOut replacement for input void dependencies")
            else:
                b.replaceOutput(r._dataVoidOut, b.buildConst(HVoidData.from_py(None)), True)
        
        if rValidPortReplacement is not None:
            b.replaceOutput(r._valid, rValidPortReplacement, True)
        if rValidNBPortReplacement is not None:
            b.replaceOutput(r._validNB, rValidNBPortReplacement, True)
        
        removed.add(r)
        removed.add(w)
        return True
