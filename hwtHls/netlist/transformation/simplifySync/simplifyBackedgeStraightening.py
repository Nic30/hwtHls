from typing import List

from hwt.pyUtils.setList import SetList
from hwtHls.netlist.analysis.ioOrdering import HlsNetlistAnalysisPassIoOrdering
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.debugTracer import DebugTracer
from hwtHls.netlist.hdlTypeVoid import HVoidData, HdlType_isVoid
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, \
    HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.transformation.simplifySync.reduceChannelGroup import netlistTryRemoveChannelGroup
from hwtHls.netlist.transformation.simplifyUtils import addAllUsersToWorklist


def netlistBackedgeStraightening(dbgTracer: DebugTracer,
                                 w: HlsNetNodeWriteBackedge,
                                 worklist: SetList[HlsNetNode],
                                 reachDb: HlsNetlistAnalysisPassReachability):
    """
    If it is possible to move write to channel before its read
    it means that the channel does not need to be backedge.
    If the extraCond, skipWhen flags are None it means that this channel does not
    even have control flow purpose and can be removed entirely.
    """
    # r is ordered before w because this is backedge
    # if w does not depend on r and none of them

    r = w.associatedRead
    if r is None:
        return False

    if r.channelInitValues:
        return False

    if w.parent is not r.parent:
        return False

    rValidPortReplacement = None
    rValidNBPortReplacement = None
    hasUsedValidNBPort = r.hasValidNB() and r.usedBy[r._validNB.out_i]
    hasUsedValidPort = r.hasValid() and r.usedBy[r._valid.out_i]
    if hasUsedValidNBPort or hasUsedValidPort:
        dataPredecs = HlsNetlistAnalysisPassIoOrdering.getDirectDataPredecessors(w)
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

    if any(reachDb.doesReachTo(rOut, w) for rOut in r._outputs if not HdlType_isVoid(rOut._dtype)):
        # [todo] ignore ordering and void data transitively
        # if write is dependent on read the channel can not be removed
        # because state of the channel state can is required
        return False

    g = w._loopChannelGroup
    isControlOfG = g is not None and g.getChannelUsedAsControl() is w
    if isControlOfG and not netlistTryRemoveChannelGroup(dbgTracer, g, worklist):
        # can not remove because it has control flow purpose
        return False

    with dbgTracer.scoped(netlistBackedgeStraightening, w):
        orderingDeps: List[HlsNetNodeOut] = []
        orderingUses: List[HlsNetNodeIn] = []
        for n in (r, w):
            for i in n.iterOrderingInputs():
                dep = n.dependsOn[i.in_i]
                if i.obj not in (r, w):
                    orderingDeps.append(dep)
                i.disconnectFromHlsOut(dep)
            oo = n.getOrderingOutPort()
            for u in n.usedBy[oo.out_i]:
                if u.obj not in (r, w):
                    orderingUses.append(u)
                u.disconnectFromHlsOut(oo)

        if orderingDeps or orderingUses:
            if len(orderingDeps) + len(orderingUses) > 1:
                # delegate ordering to successor
                raise NotImplementedError(w)
            else:
                for u in orderingUses:
                    u.obj._removeInput(u.in_i)

        # replace this read-write pair with a straight connection
        data = w.dependsOn[w._portSrc.in_i]
        w._portSrc.disconnectFromHlsOut(data, )
        rData = r._portDataOut
        b: HlsNetlistBuilder = r.getHlsNetlistBuilder()
        dbgTracer.log(("replace", rData, data))
        b.replaceOutput(rData, data, True)
        worklist.append(data.obj)
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

        r.markAsRemoved()
        w.markAsRemoved()
        if g is not None and not isControlOfG:
            g.members.remove(w)
        return True
