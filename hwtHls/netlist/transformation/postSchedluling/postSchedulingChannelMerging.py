from itertools import chain, islice
from typing import Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.schedule import HlsNetlistAnalysisPassRunScheduler
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeWriteBackwardEdge, \
    HlsNetNodeReadBackwardEdge
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.nodes.ports import _getPortDrive
from hwtHls.netlist.analysis.debugExpr import _netlistDebugExpr, \
    netlistDebugExpr


class HlsNetlistPassPostSchedulingChannelMerge(HlsNetlistPass):
    """
    For each loop search backedges scheduled in the same clock and replace them with just 1 backedge with data which is a concatenation of all backedge channel values.
    Also possibly reduce the loop input muxes and optionally reduce the data from channel entirely.
    """

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        netlist.getAnalysis(HlsNetlistAnalysisPassRunScheduler)
        # clock period number to uniq list of backedge io operaions happening there
        timeSlots: Dict[int, UniqList[HlsNetNodeExplicitSync]] = {}
        clkPeriod = netlist.normalizedClkPeriod
        for n in netlist.inputs:
            if isinstance(n, HlsNetNodeReadBackwardEdge):
                t = int(n.scheduledOut[0] // clkPeriod)
                slot = timeSlots.get(t, None)
                if slot is None:
                    slot = timeSlots[t] = UniqList()
                slot.append(n)
        removed = set()
        modified = False
        tmpVars = {}
        for _, reads in sorted(timeSlots.items(), key=lambda x: x[0]):
            for selectedI, selected in enumerate(reads):
                selected: HlsNetNodeReadBackwardEdge
                if selected in removed or selected.associated_write is None:
                    continue
                wrClkI = int(selected.associated_write.scheduledOut[0] // clkPeriod)
                toMerge = [] 
                ec = _getPortDrive(selected.extraCond)
                sw = _getPortDrive(selected.skipWhen)
                #print(selected)
                #print("    ec:", None if ec is None else netlistDebugExpr(ec, tmpVars))
                #print("    sw:", None if sw is None else netlistDebugExpr(sw, tmpVars))
                #        
                for other in islice(reads, selectedI + 1, None):
                    if other in removed:
                        continue
                    otherWr = other.associated_write
                    if otherWr is None:
                        continue
                    if (otherWr.scheduledOut[0] // clkPeriod) != wrClkI:
                        # write happens in a different time we can not merge this channels
                        continue
                    
                    _ec = _getPortDrive(other.extraCond)
                    _sw = _getPortDrive(other.skipWhen)
                    if ec is _ec and sw is _sw:
                        toMerge.append(other)

                if toMerge:
                    raise NotImplementedError(selected, toMerge)

        raise NotImplementedError()
        return modified
        
