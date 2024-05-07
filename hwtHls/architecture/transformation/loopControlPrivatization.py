from typing import Dict, Union, Tuple

from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn, \
    unlink_hls_nodes
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.netlist.nodes.archElementNoSync import ArchElementNoSync


class RtlArchPassLoopControlPrivatization(RtlArchPass):
    """
    This transformation tries to extract loop control scheme from strongly connected component of ArchElement instances.
    The goal is to write to control channels more early if possible to allow execution of another loop body iteration before
    previous one is finished if data dependency allows it.

    :note: The reason why the write to control channels is after every IO in the block even if the jump can be resolved sooner
        is that we explicitly added this ordering info 
        (in :class:`hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist.HlsNetlistAnalysisPassMirToNetlist`).
        This extra ordering info is required for FSM reconstruction. Without it the reasoning about which stages
        can be skipped when converting pipeline to FSM would be very computationally complex.
    """

    @staticmethod
    def _removeOrderingInputsViolatingScheduling(w: HlsNetNodeWriteBackedge):
        portsToRemove = []
        for inp, inpTime, dep in zip(w._inputs, w.scheduledIn, w.dependsOn):
            if dep._dtype is HVoidOrdering:
                depTime = dep.obj.scheduledOut[dep.out_i]
                if depTime > inpTime:
                    portsToRemove.append(inp)
                    unlink_hls_nodes(dep, inp)

        for port in portsToRemove:
            port: HlsNetNodeIn
            w._removeInput(port.in_i)

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        ownerOfControl: Dict[Union[HlsNetNodeWriteBackedge, HlsNetNodeReadBackedge],
                             Tuple[ArchElement, int]] = {}
        toSearch: HlsNetNodeWriteBackedge = []
        for elm in netlist.nodes:
            elm: ArchElement
            assert isinstance(elm, ArchElement), elm
            if isinstance(elm, ArchElementFsm):
                # transition table at this point should not be optimized yet
                states = elm.fsm.states

            elif isinstance(elm, ArchElementPipeline):
                states = elm.stages
            elif isinstance(elm, ArchElementNoSync):
                continue
            else:
                raise NotImplementedError(elm)

            for stI, st in enumerate(states):
                for n in st:
                    if isinstance(n, HlsNetNodeReadBackedge):
                        assert n not in ownerOfControl, (n, ownerOfControl[n], (elm, stI))
                        ownerOfControl[n] = (elm, stI)

                    elif isinstance(n, HlsNetNodeWriteBackedge):
                        assert n not in ownerOfControl, (n, ownerOfControl[n], (elm, stI))
                        ownerOfControl[n] = (elm, stI)
                        toSearch.append(n)

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
                    if jumpSrcVal.obj in headerElm._subNodes or (
                            jumpSrcValStI >= headerElm._beginClkI and
                            jumpSrcValStI <= headerElm._endClkI):
                        if headerElm is tailElm and wStI == len(headerElm.fsm.states) - 1:
                            pass  # skip moving to same stage in the same element
                        else:
                            headerElm._subNodes.append(w)
                            headerElm.fsm.states[-1].append(w)
                            t = (headerElm._endClkI + 1) * clkPeriod - ffdelay
                            assert wMinTime <= t, (w, wMinTime, t)
                            w.moveSchedulingTime(t - w.scheduledZero)
                            removeFromTail = True

                elif isinstance(headerElm, ArchElementPipeline):
                    if jumpSrcVal.obj in headerElm._subNodes:
                        headerElm._subNodes.append(w)
                        t = max(wMinTime, jumpSrcValT)
                        newStI = start_clk(t, clkPeriod)
                        if newStI != wStI:
                            w.moveSchedulingTime(t - w.scheduledZero)
                            headerElm.stages[newStI].append(w)
                            removeFromTail = True
                else:
                    raise NotImplementedError(headerElm)

                if removeFromTail:
                    # disconnect all ordering inputs which are not satisfying timing because we have just moved
                    # the node ignoring void connections
                    self._removeOrderingInputsViolatingScheduling(w)

                    if isinstance(tailElm, ArchElementFsm):
                        # rm write node from current element
                        if headerElm is not tailElm:
                            tailElm._subNodes.remove(w)
                        tailElm.fsm.states[wStI].remove(w)
                        if wStI != len(tailElm.fsm.states) - 1:
                            raise NotImplementedError("This jump in CFG was not in last state and can be used to optimize tailElm"
                                                      " but we now removed it, we should add a local version of this instead", w)

                    elif isinstance(tailElm, ArchElementPipeline):
                        if headerElm is not tailElm:
                            tailElm._subNodes.remove(w)
                        tailElm.stages[wStI].remove(w)
                    else:
                        raise NotImplementedError(headerElm)
                w.checkScheduling()
