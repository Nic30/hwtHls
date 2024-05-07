from typing import List, Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement, ArchElmEdge
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementUtils import ArchElement_mergeFsms
from hwtHls.netlist.scheduler.clk_math import start_clk


# from hwtHls.netlist.nodes.const import HlsNetNodeConst
class RtlArchPassMergeTiedFsms(RtlArchPass):
    """
    If multiple FSMs are running in parallel but there is an non-optional communication between them in multiple states
    one FSM control logic may be redundant if the state transitions are same.
    """

    # @staticmethod
    # def _copyFsmTransitionIfRequired(srcFsm: ArchElementFsm, dstFsm: ArchElementFsm, stClk: int,
    #                                 justAddedTransitions: Set[Tuple[ArchElementFsm, int, int]]):
    #    """
    #    :param justAddedTransitions: set of tuples (fsm, srcClkI, dstClkI)
    #    """
    #    dstSt = dstFsm.fsm.clkIToStateI[stClk]
    #    for nextSt, nextStCond in sorted(srcFsm.fsm.transitionTable[srcFsm.fsm.clkIToStateI[stClk]].items(), key=lambda x: x[0]):
    #        nextStClk = srcFsm.fsm.stateClkI[nextSt]
    #        try:
    #            if nextStClk < dstFsm._beginClkI:
    #                # the FSM as a whole restarts
    #                nextStClk = dstFsm._beginClkI
    #            if nextStClk == srcFsm._beginClkI and (srcFsm._endClkI < dstFsm._endClkI or
    #                                                   srcFsm._beginClkI > dstFsm._beginClkI):
    #                # if this is an implicit reset in srcFsm which and other dstFsm contains this FSM
    #                continue
    #            if (srcFsm, stClk, nextStClk) in justAddedTransitions:
    #                # to avoid duplication due to transitive adding of transitions
    #                continue
    #
    #            dstNextSt = dstFsm.fsm.clkIToStateI[nextStClk]
    #
    #        except KeyError:
    #            # the state does not exists in the target there is no risk of deadlock from waiting on sync in that (non existing) state
    #            continue
    #
    #        curCond = dstFsm.fsm.transitionTable[dstSt].get(dstNextSt, None)
    #        if (curCond is None or isinstance(curCond, (bool, int))) and curCond is not nextStCond:
    #            curTransitions = dstFsm.fsm.transitionTable[dstSt]
    #            if nextStCond == 1:
    #                # if there is any unconditional transition to soner state
    #                # got to sooner state and
    #                curTransitions[dstNextSt] = nextStCond
    #            justAddedTransitions.add((dstFsm, stClk, nextStClk))

    @staticmethod
    def _elmInsideOfTimeIntervalOfOther(child: ArchElement, parent: ArchElement):
        if parent._beginClkI <= child._beginClkI:
            # child in parent
            return child._endClkI <= parent._endClkI
        # elif child._endClkI >= parent._endClkI:
        #    # parent in child
        #    return child._beginClkI <= parent._beginClkI
        else:
            return False

    @staticmethod
    def _getFinalElement(elmMergedInto: Dict[ArchElementFsm, ArchElementFsm], elm: ArchElementFsm):
        while True:
            _elm = elmMergedInto.get(elm, None)
            if _elm is None:
                return elm
            elm = _elm

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        # find all deadlocking FSMs due to missing state transition
        clkPeriod = netlist.normalizedClkPeriod
        syncMatrix: Dict[ArchElmEdge, List[int]] = {}
        fsmConnectedWithMultipleSync: UniqList[ArchElmEdge] = UniqList()
        for elm in netlist.nodes:
            assert isinstance(elm, ArchElement), elm
            for dep, users in zip(elm._outputs, elm.usedBy):
                for use in users:
                    srcElm = dep.obj
                    dstElm = use.obj
                    k = (srcElm, dstElm)
                    syncClks = syncMatrix.get(k, None)
                    if syncClks is None:
                        syncClks = syncMatrix[k] = set()
                    elif len(syncClks) == 1:
                        fsmConnectedWithMultipleSync.append(k)

                    clkI = start_clk(use.obj.scheduledIn[use.in_i], clkPeriod)
                    syncClks.add(clkI)

        # for dstElm in netlist.nodes:
        #    dstElm: ArchElement
        #    for n in dstElm._subNodes:
        #        n: HlsNetNode
        #        for dep, useTime in zip(n.dependsOn, n.scheduledIn):
        #            if depElm is not dstElm:
        #                useClk = useTime =
        #                raise NotImplementedError()

        # iterate left top of
        # for elm in netlist.nodes:
        #     elm: ArchElement
        #     for con in elm.connections:
        #         con: ConnectionsOfStage
        #         for o, _ in con.outputs:
        #             if isinstance(o, ArchChannelSync):
        #                 o: ArchChannelSync
        #                 assert elm is o.srcElm, (elm, o, o.srcElm)
        #                 k = (o.srcElm, o.dstElm)
        #                 syncList = syncMatrix.get(k, None)
        #                 if syncList is None:
        #                     syncList = syncClkIs = []
        #                 elif len(syncList) == 1:
        #                     fsmConnectedWithMultipleSync.append(k)
        #
        #                 syncList.append(o)

        elmMergedInto: Dict[ArchElementFsm, ArchElementFsm] = {}
        for k in fsmConnectedWithMultipleSync:
            elm0, elm1 = k
            if isinstance(elm0, ArchElementFsm) and isinstance(elm1, ArchElementFsm):
                elm0: ArchElementFsm = self._getFinalElement(elmMergedInto, elm0)
                elm1: ArchElementFsm = self._getFinalElement(elmMergedInto, elm1)
                if elm0 is elm1:
                    # skip because it is already merged
                    continue

                if self._elmInsideOfTimeIntervalOfOther(elm1, elm0):
                    ArchElement_mergeFsms(elm1, elm0)
                    elmMergedInto[elm1] = elm0

                elif self._elmInsideOfTimeIntervalOfOther(elm1, elm0):
                    ArchElement_mergeFsms(elm0, elm1)
                    elmMergedInto[elm0] = elm1

                else:
                    # share common state transitions
                    pass
                    # for clkIndex in syncClkIs:
                    #    self._copyFsmTransitionIfRequired(elm0, elm1, clkIndex, addedTransitions)
                    #    self._copyFsmTransitionIfRequired(elm1, elm0, clkIndex, addedTransitions)

        netlist.filterNodesUsingSet(elmMergedInto, recursive=True)
