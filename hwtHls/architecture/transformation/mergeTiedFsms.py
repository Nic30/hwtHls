from itertools import islice
from typing import List, Dict, Tuple, Union, Set

from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass


ArchElmEdge = Tuple[ArchElement, ArchElement]


class RtlArchPassMergeTiedFsms(RtlArchPass):
    """
    If multiple FSMs are running in parallel but there is an non-optional communication between them in multiple states
    one FSM control logic may be redundant if the state transitions are same.
    """

    #def _copyFsmTransitionIfRequired(self, srcFsm: ArchElementFsm, dstFsm: ArchElementFsm, stClk: int,
    #                                 justAddedTransitions: Set[Tuple[ArchElementFsm, int, int]]):
    #    """
    #    :param justAddedTransitions: set of tuples (fsm, srcClkI, dstClkI)
    #    """
    #    dstSt = dstFsm.fsm.clkIToStateI[stClk]
    #    for nextSt, nextStCond in sorted(srcFsm.fsm.transitionTable[srcFsm.fsm.clkIToStateI[stClk]].items(), key=lambda x: x[0]):
    #        nextStClk = srcFsm.fsm.stateClkI[nextSt]
    #        try:
    #            if nextStClk < dstFsm.fsmBeginClk_i:
    #                # the FSM as a whole restarts
    #                nextStClk = dstFsm.fsmBeginClk_i
    #            if nextStClk == srcFsm.fsmBeginClk_i and (srcFsm.fsmEndClk_i < dstFsm.fsmEndClk_i or
    #                                                      srcFsm.fsmBeginClk_i > dstFsm.fsmBeginClk_i):
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
    #            dstFsm.fsm.transitionTable[dstSt][dstNextSt] = nextStCond
    #            justAddedTransitions.add((dstFsm, stClk, nextStClk))

    def apply(self, hls: "HlsScope", allocator: HlsAllocator):
        # find all deadlocking FSMs due to missing state transition
        syncMatrix: Dict[ArchElmEdge, List[InterArchElementHandshakeSync]] = {}
        fsmConnectedWithMultipleSync: List[ArchElmEdge] = []
        # iterate left top of  
        for elm in allocator._archElements:
            elm: ArchElement
            for con in elm.connections:
                con: ConnectionsOfStage
                for o, _ in con.outputs:
                    if isinstance(o, InterArchElementHandshakeSync):
                        o: InterArchElementHandshakeSync
                        assert elm is o.srcElm, (elm, o, o.srcElm)
                        k = (o.srcElm, o.dstElm)
                        syncList = syncMatrix.get(k, None)
                        if syncList is None:
                            syncList = syncMatrix[k] = []
                        elif len(syncList) == 1:
                            fsmConnectedWithMultipleSync.append(k)

                        syncList.append(o)

        addedTransitions: Set[Tuple[ArchElementFsm, int, int]] = set()
        RtlArchPassMergeTiedFsms
        for k in fsmConnectedWithMultipleSync:
            srcElm, dstElm = k
            if isinstance(srcElm, ArchElementFsm) and isinstance(dstElm, ArchElementFsm):
                srcElm: ArchElementFsm
                dstElm: ArchElementFsm
                for sync in syncMatrix[k]:
                    sync: InterArchElementHandshakeSync
                    self._copyFsmTransitionIfRequired(srcElm, dstElm, sync.clkIndex, addedTransitions)
                    self._copyFsmTransitionIfRequired(dstElm, srcElm, sync.clkIndex, addedTransitions)

