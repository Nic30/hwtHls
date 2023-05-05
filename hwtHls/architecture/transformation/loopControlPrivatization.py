from typing import Dict, Union, Tuple

from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.orderable import HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import start_clk


class RtlArchPassLoopControlPrivatization(RtlArchPass):
    """
    This transformation tries to extract loop control scheme from strongly connected component of ArchElement instances.
    The goal is to write to control channels more early if possible to allow execution of another loop body iteration before
    previous one is finished if data dependency allows it.

    :note: The reason why the write to control channels is after every IO in the block even if the jump can be resolved sooner
        is that we explicitly added this ordering info (in :class:`hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist.HlsNetlistAnalysisPassMirToNetlist`).
        This extra ordering info is required for FSM reconstruction. Without it the reasoning about which stages can be skipped when converting pipeline to FSM
        would be very computationally complex.
    """

    def apply(self, hls:"HlsScope", allocator:HlsAllocator):
        ownerOfControl: Dict[Union[HlsNetNodeWriteBackedge, HlsNetNodeReadBackedge],
                             Tuple[ArchElement, int]] = {}
        toSearch: HlsNetNodeWriteBackedge = []
        for elm in allocator._archElements:
            elm: ArchElement
            assert elm.interArchAnalysis is None, "This must be done before IAEA analysis because this does not update it"
            if isinstance(elm, ArchElementFsm):
                # transition table at this point should not be optimized yet
                states = elm.fsm.states

            elif isinstance(elm, ArchElementPipeline):
                states = elm.stages

            else:
                raise NotImplementedError(elm)

            for stI, st in enumerate(states):
                for n in st:
                    if isinstance(n, HlsNetNodeReadBackedge):
                        assert n not in ownerOfControl, n
                        ownerOfControl[n] = (elm, stI)

                    elif isinstance(n, HlsNetNodeWriteBackedge):
                        assert n not in ownerOfControl, n
                        ownerOfControl[n] = (elm, stI)
                        toSearch.append(n)

        netlist = allocator.netlist
        scheduler = netlist.scheduler
        epsilon = scheduler.epsilon
        clkPeriod = netlist.normalizedClkPeriod
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, scheduler.resolution)
        for w in toSearch:
            # because it is instance of HlsNetNodeWriteBackedge we know it is some form of jump from loop body to loop header.
            w: HlsNetNodeWriteBackedge
            r: HlsNetNodeReadBackedge = w.associatedRead
            jumpSrcVal: HlsNetNodeOut = w.dependsOn[0]
            jumpSrcValT: int = jumpSrcVal.obj.scheduledOut[jumpSrcVal.out_i]
            if jumpSrcValT < w.scheduledIn[0] - epsilon:
                headerElm, rStI = ownerOfControl[r]
                headerElm: ArchElement
                tailElm, wStI = ownerOfControl[w]
                tailElm: ArchElement
                if headerElm is tailElm and isinstance(headerElm, ArchElementFsm):
                    # this does not cross element boundary and will be handled internally in FSM
                    continue

                wMinTime = None  # minimum time for "w" where all requirements are met
                for wDep in w.dependsOn:
                    wDep: HlsNetNodeOut
                    if wDep._dtype is not HVoidOrdering:
                        t = wDep.obj.scheduledOut[wDep.out_i]
                        if wMinTime is None:
                            wMinTime = t
                        else:
                            wMinTime = max(wMinTime, t)

                assert wMinTime is not None, w

                jumpSrcValStI = start_clk(jumpSrcValT, clkPeriod)
                removeFromTail = False
                if isinstance(headerElm, ArchElementFsm):
                    headerElm: ArchElementFsm
                    if jumpSrcVal.obj in headerElm.allNodes or (
                            jumpSrcValStI >= headerElm.fsmBeginClk_i and
                            jumpSrcValStI <= headerElm.fsmEndClk_i):
                        if headerElm is tailElm and wStI == len(headerElm.fsm.states) - 1:
                            pass  # skip moving to same stage in the same element
                        else:
                            headerElm.allNodes.append(w)
                            headerElm.fsm.states[-1].append(w)
                            t = (headerElm.fsmEndClk_i + 1) * clkPeriod - ffdelay
                            assert wMinTime <= t, (w, wMinTime, t)
                            w.scheduledIn = tuple(t for _ in w._inputs)
                            w.scheduledOut = tuple(t + epsilon for _ in w._outputs)
                            removeFromTail = True

                elif isinstance(headerElm, ArchElementPipeline):
                    if jumpSrcVal.obj in headerElm.allNodes:
                        headerElm.allNodes.append(w)
                        t = max(wMinTime, jumpSrcValT)
                        newStI = start_clk(t, clkPeriod)
                        if newStI != wStI:
                            w.scheduledIn = tuple(t for _ in w._inputs)
                            w.scheduledOut = tuple(t + epsilon for _ in w._outputs)
                            headerElm.stages[newStI].append(w)
                            removeFromTail = True
                else:
                    raise NotImplementedError(headerElm)

                if removeFromTail:
                    if isinstance(tailElm, ArchElementFsm):
                        # rm write node from current element
                        if headerElm is not tailElm:
                            tailElm.allNodes.remove(w)
                        tailElm.fsm.states[wStI].remove(w)
                        if wStI != len(tailElm.fsm.states) - 1:
                            raise NotImplementedError("This jump in CFG was not in last state and can be used to optimize tailElm but we now removed it, we should add a local version of this instead", w)

                    elif isinstance(tailElm, ArchElementPipeline):
                        if headerElm is not tailElm:
                            tailElm.allNodes.remove(w)
                        tailElm.stages[wStI].remove(w)
                    else:
                        raise NotImplementedError(headerElm)

