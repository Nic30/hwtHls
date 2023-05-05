from typing import List, Dict, Tuple, Set

from hwt.pyUtils.uniqList import UniqList
from hwtHls.architecture.allocator import HlsAllocator
from hwtHls.architecture.archElement import ArchElement, ArchElmEdge
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.analysis.detectFsms import IoFsm
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isVoid
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.netlist.nodes.const import HlsNetNodeConst


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

    @classmethod
    def _mergeFsms(cls, iea: InterArchElementNodeSharingAnalysis,
                   syncClkIs: List[int],
                   addedTransitions: Set[Tuple[ArchElementFsm, int, int]],
                   srcElm: ArchElementFsm, dstElm: ArchElementFsm):
        # for clkIndex in syncClkIs:
        #    cls._copyFsmTransitionIfRequired(srcElm, dstElm, clkIndex, addedTransitions)

        firstUseTimeOfOutInElem = iea.firstUseTimeOfOutInElem
        ownerOfInput = iea.ownerOfInput
        ownerOfOutput = iea.ownerOfOutput
        ownerOfNode = iea.ownerOfNode
        for n in srcElm.allNodes:
            n: HlsNetNode
            for dep, i in zip(n.dependsOn, n._inputs):
                if HdlType_isVoid(dep._dtype):
                    continue
                #elif isinstance(dep.obj, HlsNetNodeConst):
                #    continue
                tSrc = firstUseTimeOfOutInElem.pop((srcElm, dep), None)
                k = (dstElm, dep)
                if tSrc is None:
                    assert k not in firstUseTimeOfOutInElem, (k, "if this is only this ArchElement internal, it should be internal everywhere")
                else:
                    tDst = firstUseTimeOfOutInElem.get(k, tSrc)
                    t = min(tSrc, tDst)
                    firstUseTimeOfOutInElem[k] = t

                cur = ownerOfInput[i]
                cur.remove(srcElm)
                cur.append(dstElm)

            for o in n._outputs:
                if HdlType_isVoid(o._dtype):
                    continue

                cur = ownerOfOutput.pop(o)
                assert cur is srcElm
                ownerOfOutput[o] = dstElm

            cur = ownerOfNode.pop(n)
            assert cur is srcElm, (n, cur, srcElm)
            ownerOfNode[n] = dstElm

        update = {}
        for k, v in iea.explicitPathSpec.items():
            o, i, elm = k
            if elm is srcElm:
                update[(o, i, dstElm)] = v
        iea.explicitPathSpec.update(update)
        dstElm.allNodes.extend(srcElm.allNodes)

        srcFsm: IoFsm = srcElm.fsm
        dstFsm: IoFsm = dstElm.fsm
        # rename FSM states in FSM to match names in dst
        for srcClk, srcSt in enumerate(srcFsm.states):
            dstSt = dstFsm.addState(srcClk)
            dstSt.extend(srcSt)
            dstFsm.syncIslands.extend(srcFsm.syncIslands)
            dstElm.connections[srcClk].merge(srcElm.connections[srcClk])

        dstFsm.intf = None

    @staticmethod
    def _getFinalElement(elmMergedInto: Dict[ArchElementFsm, ArchElementFsm], elm: ArchElementFsm):
        while True:
            _elm = elmMergedInto.get(elm, None)
            if _elm is None:
                return elm
            elm = _elm

    def apply(self, hls: "HlsScope", allocator: HlsAllocator):
        # find all deadlocking FSMs due to missing state transition
        iea: InterArchElementNodeSharingAnalysis = allocator._iea
        ownerOfNode = iea.ownerOfNode
        clkPeriod = allocator.netlist.normalizedClkPeriod
        # useT = iea.firstUseTimeOfOutInElem[(dstElm, o)]
        # dstUseClkI = start_clk(useT, clkPeriod)
        firstUseTimeOfOutInElem = iea.firstUseTimeOfOutInElem

        syncMatrix: Dict[ArchElmEdge, List[int]] = {}
        fsmConnectedWithMultipleSync: UniqList[ArchElmEdge] = UniqList()
        for dep, use in iea.interElemConnections:
            srcElm = ownerOfNode[dep.obj]
            dstElm = ownerOfNode[use.obj]
            k = (srcElm, dstElm)
            syncClks = syncMatrix.get(k, None)
            if syncClks is None:
                syncClks = syncMatrix[k] = set()
            elif len(syncClks) == 1:
                fsmConnectedWithMultipleSync.append(k)

            clkI = start_clk(firstUseTimeOfOutInElem[(dstElm, dep)], clkPeriod)
            syncClks.add(clkI)

        # for dstElm in allocator._archElements:
        #    dstElm: ArchElement
        #    for n in dstElm.allNodes:
        #        n: HlsNetNode
        #        for dep, useTime in zip(n.dependsOn, n.scheduledIn):
        #            if depElm is not dstElm:
        #                useClk = useTime =
        #                raise NotImplementedError()

        # iterate left top of
        # for elm in allocator._archElements:
        #     elm: ArchElement
        #     for con in elm.connections:
        #         con: ConnectionsOfStage
        #         for o, _ in con.outputs:
        #             if isinstance(o, InterArchElementHandshakeSync):
        #                 o: InterArchElementHandshakeSync
        #                 assert elm is o.srcElm, (elm, o, o.srcElm)
        #                 k = (o.srcElm, o.dstElm)
        #                 syncList = syncMatrix.get(k, None)
        #                 if syncList is None:
        #                     syncList = syncClkIs = []
        #                 elif len(syncList) == 1:
        #                     fsmConnectedWithMultipleSync.append(k)
        #
        #                 syncList.append(o)

        addedTransitions: Set[Tuple[ArchElementFsm, int, int]] = set()
        elmMergedInto: Dict[ArchElementFsm, ArchElementFsm] = {}
        for k in fsmConnectedWithMultipleSync:
            elm0, elm1 = k
            if isinstance(elm0, ArchElementFsm) and isinstance(elm1, ArchElementFsm):
                elm0: ArchElementFsm = self._getFinalElement(elmMergedInto, elm0)
                elm1: ArchElementFsm = self._getFinalElement(elmMergedInto, elm1)
                if elm0 is elm1:
                    # skip because it is already merged
                    continue
                syncClkIs = sorted(syncMatrix[k])
                if self._elmInsideOfTimeIntervalOfOther(elm1, elm0):
                    self._mergeFsms(iea, syncClkIs, addedTransitions, elm1, elm0)
                    elmMergedInto[elm1] = elm0

                elif self._elmInsideOfTimeIntervalOfOther(elm1, elm0):
                    self._mergeFsms(iea, syncClkIs, addedTransitions, elm0, elm1)
                    elmMergedInto[elm0] = elm1

                else:
                    # share common state transitions
                    pass
                    # for clkIndex in syncClkIs:
                    #    self._copyFsmTransitionIfRequired(elm0, elm1, clkIndex, addedTransitions)
                    #    self._copyFsmTransitionIfRequired(elm1, elm0, clkIndex, addedTransitions)

        allocator._archElements = [elm for elm in allocator._archElements if elm not in elmMergedInto]
