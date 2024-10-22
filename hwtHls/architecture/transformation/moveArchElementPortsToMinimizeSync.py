from typing import Tuple, Dict, Set

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    INVARIANT_TIME
from hwtHls.architecture.transformation.addImplicitSyncChannels import SyncCacheKey
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregatePorts import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.node import NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import start_clk, endOfClkWindow, \
    beginOfClkWindow
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class HlsArchPassMoveArchElementPortsToMinimizeSync(HlsArchPass):
    """
    This pass reschedules ArchElement ports to minimize number of clock cycles where the data is exchanged between elements.
    For example, a value is passes to other element once it is required in there.
    However the value may be potentially transfered sooner with other data and synchronization in that cycle may be avoided.
    There are several cases where it is beneficial to modify time when data is moved described in this code.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        changed = False
        archElements = [elm for elm in netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.ONLY_PARENT_PREORDER) if elm is not netlist]
        # nonOptionalClkWindows: Set[Tuple[ArchElement, int]] = set()
        clkPeriod = netlist.normalizedClkPeriod
        for elm in archElements:
            elm: ArchElement
            if isinstance(elm, ArchElementPipeline):
                for o, uses in zip(elm._outputs, elm.usedBy):
                    defTime = elm.scheduledOut[o.out_i]  # can not be in zip because it may change during iteration
                    defClk = defTime // clkPeriod
                    # resolve maximum value of use time,
                    # it is the maximum time where output time may potentially shift
                    realMaxUseTimeMax = endOfClkWindow(elm._endClkI, clkPeriod)
                    for u in uses:
                        u: HlsNetNodeIn
                        useObj: ArchElement = u.obj
                        useTime = useObj.scheduledIn[u.in_i]

                        if isinstance(useObj, ArchElementPipeline):
                            useClk = useTime // clkPeriod
                            earliestUseOfUserInput = min(u.obj.scheduledIn[u.in_i] for u in useObj._inputsInside[u.in_i].usedBy[0])
                            earliestUseOfUserInputClk = earliestUseOfUserInput // clkPeriod
                            if earliestUseOfUserInputClk != useClk:
                                # check if this clock window is occupied only nodes without side-effect
                                userClockWindowSkipable = True
                                while userClockWindowSkipable:
                                    for n in useObj.getStageForClock(useClk):
                                        if not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeConst)):
                                            userClockWindowSkipable = False
                                            break

                                    if userClockWindowSkipable:
                                        useClk += 1
                                    else:
                                        break
                                # useClk is now the the clock window index at where the first node with side-effect is
                                useTime = min(earliestUseOfUserInput, endOfClkWindow(useClk, clkPeriod))

                        realMaxUseTimeMax = min(realMaxUseTimeMax, useTime)

                    newDefClkIndex = realMaxUseTimeMax // clkPeriod
                    elmentsWithRescheduledInputs: SetList[ArchElement] = SetList()
                    newTime = beginOfClkWindow(newDefClkIndex, clkPeriod)
                    if defClk != newDefClkIndex:
                        for u in uses:
                            u: HlsNetNodeIn
                            useObj: ArchElement = u.obj
                            if isinstance(useObj, ArchElementPipeline):
                                self._rescheduledArchElementPort(useObj, u, newDefClkIndex, newTime, clkPeriod)
                                elmentsWithRescheduledInputs.append(useObj)

                        for user in elmentsWithRescheduledInputs:
                            user.copySchedulingFromChildren()

                        # update time of output
                        self._rescheduledArchElementPort(elm, o, newDefClkIndex, newTime, clkPeriod)

                        elm.copySchedulingFromChildren()

        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()

    @staticmethod
    def _rescheduledArchElementPort(elm: ArchElementPipeline, p: HlsNetNodeIn, newClkI: int, newTime: SchedTime, clkPeriod: SchedTime):
        isIn = isinstance(p, HlsNetNodeIn)
        if isIn:
            portInside: HlsNetNodeAggregatePortIn = elm._inputsInside[p.in_i]
        else:
            portInside: HlsNetNodeAggregatePortOut = elm._outputsInside[p.out_i]
        # update time of user input
        portClkI = (elm.scheduledIn[p.in_i] if isIn else elm.scheduledOut[p.out_i]) // clkPeriod
        assert newClkI > portClkI, (p, portClkI, newClkI)
        clkWindowList = elm.getStageForClock(portClkI)
        clkWindowList.remove(portInside)
        if elm._beginClkI == portClkI:
            clkI = portClkI
            while True:
                # check if clkWindowList is empty or nodes can be scheduled in later clk window
                if all(isinstance(n, HlsNetNodeConst) for n in clkWindowList):
                    # reschedule all constants to clock window where it is first used the first time
                    endTime = endOfClkWindow(elm._endClkI, clkPeriod)
                    for n in clkWindowList:
                        if not n.usedBy:
                            n.markAsRemoved()
                        else:
                            for _ in n.scheduleAlapCompaction(endTime, None, None):
                                pass

                            elm.getStageForClock(n.scheduledZero // clkPeriod).append(n)

                    clkWindowList.clear()

                if not clkWindowList:
                    elm.removeStage(clkI)
                    if elm._beginClkI == newClkI:
                        # do not attempt to remove the clock windows where this port would be rescheduled to
                        break
                    # search also if next clock window is not empty
                    clkI = elm._beginClkI
                    clkWindowList = elm.getStageForClock(clkI)
                else:
                    break

        elm.getStageForClock(newClkI).append(portInside)
        portInside._setScheduleZero(newTime)

    # def _handleInterArchElementPropagation(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
    #    """
    #    Depending on occupation of clock windows in element it may be beneficial to
    #    move input port to earlier time or output to later time.
    #    The data of output are not consumed so it is safe to move input/output in any position regardless of loops.
    #    However care must be taken for FSM because it can skip clock window entirely so data
    #    would not be copied into it if state is not executed.
    #    """
    #    netlist = o.obj.netlist
    #    clkPeriod = netlist.normalizedClkPeriod
    #    dstElm: ArchElement = i.obj
    #    useT = dstElm.scheduledIn[i.in_i]
    #    defTime = o.obj.scheduledOut[o.out_i]
    #    assert defTime <= useT, (defTime, useT, o)
    #    srcStartClkI = start_clk(defTime, clkPeriod)
    #    dstUseClkI = start_clk(useT, clkPeriod)
    #    if isinstance(dstElm, ArchElementFsm):
    #        assert dstElm.fsm.hasUsedStateForClkI(dstUseClkI), (
    #            dstUseClkI, o, "Output must be scheduled to some cycle corresponding to fsm state")
    #
    #    if srcStartClkI == dstUseClkI:
    #        return False
    #
    #    srcElm: ArchElement = o.obj
    #    # it is required to add buffers somewhere to latch the value to that time
    #    # we prefer adding the registers to pipelines because it may result in better performance
    #    epsilon: int = netlist.scheduler.epsilon
    #    if isinstance(srcElm, ArchElementFsm) and not srcElm.fsm.hasUsedStateForClkI(dstUseClkI):
    #        srcElm: ArchElementFsm
    #        raise NotImplementedError("[todo] update from use of InterElementAnalysis to HlsNetNodeAggregatePort")
    #        if isinstance(dstElm, ArchElementPipeline):
    #            # extend the life of the variable in FSM if possible
    #            # optionally move first use closer to begin of pipeline or even prepend stages for pipeline
    #            # to be able to accept the src data when it exists
    #            assert srcElm.fsm.hasUsedStateForClkI(srcStartClkI), (srcElm, srcStartClkI)
    #            closestClockIWithState = srcStartClkI
    #            for clkI in range(srcStartClkI, dstUseClkI + 1):
    #                if srcElm.fsm.states[clkI]:
    #                    closestClockIWithState = clkI
    #            newUseT = closestClockIWithState * clkPeriod + epsilon
    #            assert newUseT <= useT, (useT, newUseT, o)
    #            assert defTime <= newUseT, (defTime, newUseT, o)
    #            #iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
    #            return True
    #
    #        elif isinstance(dstElm, ArchElementFsm):
    #            dstElm: ArchElementFsm
    #            # find overlaps in schedulization of FSMs
    #            beginClkI = max(srcElm._beginClkI, dstElm._beginClkI)
    #            endClkI = min(srcElm._endClkI, dstElm._endClkI)
    #            sharedClkI = None
    #            if beginClkI > endClkI:
    #                # no overlap
    #                pass
    #            else:
    #                for clkI in range(beginClkI, endClkI + 1):
    #                    if clkI * clkPeriod > defTime and srcElm.fsm.hasUsedStateForClkI(clkI) and dstElm.fsm.hasUsedStateForClkI(clkI):
    #                        sharedClkI = clkI
    #                        break
    #
    #            if sharedClkI is not None:
    #                # if src and dst FSM overlaps exactly in 1 time we can safely transfer data there
    #                clkT = sharedClkI * clkPeriod
    #                assert clkT <= useT, (o, clkT, useT)
    #                newUseT = min(clkT + epsilon, useT)
    #                #iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
    #                assert newUseT <= useT, (useT, newUseT, o)
    #                assert defTime <= newUseT, (defTime, newUseT, o)
    #                return True
    #
    #            else:
    #                # if dst and src FSM does not overlap at all we must create a buffer
    #                # [todo] however we must write to this channel only conditionally, if it is sure that the CFG will not avoid successor elements
    #                # Need to add extra buffer between FSMs or move value load/store in states
    #                # We add new pipeline to architecture and register this pair to interElemConnections
    #                #k = (srcElm, srcStartClkI, dstElm, dstUseClkI)
    #                #p = interElementBufferPipelines.get(k, None)
    #                #if p is None:
    #                #    # [todo] this can be used only if there is a common predecessor to multiple arch elements
    #                #    #        and we want to spare resources
    #                #    #        it can not be used only if the consumption of this data is unconditional
    #                #    #        * This is required because we distributed CFG to multiple arch elements and once we send
    #                #    #          data to the element the data must also be consumed in order to avoid deadlock
    #                #    srcBaseName = self._getArchElmBaseName(srcElm)
    #                #    dstBaseName = self._getArchElmBaseName(dstElm)
    #                #    bufferPipelineName = f"{self.name:s}buffer_{srcBaseName:s}{srcStartClkI}_to_{dstBaseName:s}{dstUseClkI}"
    #                #    stages = [[] for _ in range(start_clk(useT, clkPeriod) + 1)]
    #                #    p = ArchElementPipeline(self.netlist, bufferPipelineName, stages, None)
    #                #    self._archElements.append(p)
    #                #    interElementBufferPipelines[k] = p
    #
    #                # [todo] if src is ArchElementFsm it may be possible (if it is guaranteed that the register will not be written)
    #                #        to extend register life to shorten the buffer
    #                # [todo] it may be possible to move value to dstElm sooner if CFG and scheduling allows this
    #                #synonyms = iea.portSynonyms.get(o, ())
    #                #defT = o.obj.scheduledOut[o.out_i]
    #                #iea.explicitPathSpec[(o, i, dstElm)] = [ValuePathSpecItem(p, defT, useT), ]
    #                #iea.firstUseTimeOfOutInElem[(p, o)] = defT
    #                #addOutputAndAllSynonymsToElement(o, defT, synonyms, p, self.netlist.normalizedClkPeriod)
    #                return True
    #        else:
    #            raise NotImplementedError("Propagating the value to element of unknown type", dstElm)
    #
    #    return False
    #
    #def extendValidityOfRtlResource(self, tir: TimeIndependentRtlResource, endTime: float):
    #    assert self._rtlDatapathAllocated
    #    assert not self._rtlSyncAllocated
    #    assert tir.timeOffset is not INVARIANT_TIME
    #    assert endTime > tir.timeOffset, (tir, tir.timeOffset, endTime)
    #
    #    clkPeriod = self.netlist.normalizedClkPeriod
    #    t = tir.timeOffset + (len(tir.valuesInTime) - 1) * clkPeriod + self.netlist.scheduler.epsilon
    #    assert t < endTime
    #    # :note: done in reverse so we do not have to always iterate over registered prequel
    #    while t <= endTime:
    #        t += clkPeriod
    #        i = int(t // clkPeriod)
    #        if i >= len(self.connections):
    #            self.stages.append([])
    #            self.connections.append(ConnectionsOfStage(self, i))
    #
    #        sigs = self.connections.getForClkIndex(i).signals
    #        assert tir not in sigs
    #        tir.get(t)
    #        sigs.append(tir)

    #def finalizeInterElementsConnections(self):
    #    """
    #    Resolve a final value when the data will be exchanged between arch. element instances
    #    """
    #
    #    syncAdded: Set[SyncCacheKey] = {}
    #    tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]] = set()
    #    elementIndex: Dict[ArchElement, int] = {a: i for i, a in enumerate(self.netlist.nodes)}
    #    for srcElm in self.netlist.nodes:
    #        srcElm: ArchElement
    #        for o, uses in zip(srcElm._outputs, srcElm.usedBy):
    #            o: HlsNetNodeOut
    #            if HdlType_isVoid(o._dtype):
    #                continue
    #            for i in uses:
    #                i: HlsNetNodeIn
    #                dstElm = i.obj
    #                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
    #                if dstTir.valuesInTime[0].data.drivers:
    #                    # the value is already propagated to dstElm
    #                    continue
    #
    #                # src should be already declared form ArchElement.rtlAllocDatapath or declareInterElemenetBoundarySignals
    #                srcTir: TimeIndependentRtlResource = srcElm.netNodeToRtl[o]
    #                # dst should be already declared from declareInterElemenetBoundarySignals
    #                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
    #                self._finalizeInterElementsConnection(o, srcTir, dstTir, srcElm, dstElm, elementIndex, syncAdded, tirsConnected)
    #
    #def _finalizeInterElementsConnection(self, o: HlsNetNodeOut,
    #                                     srcTir: TimeIndependentRtlResource, dstTir: TimeIndependentRtlResource,
    #                                     srcElm: ArchElement, dstElm: ArchElement,
    #                                     elementIndex: Dict[ArchElement, int],
    #                                     syncAdded: Set[SyncCacheKey],
    #                                     tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]]):
    #    if (srcTir, dstTir) in tirsConnected:
    #        # because the signal may have aliases there may be signals of same value which are sing same TimeIndependentRtlResource
    #        return
    #    else:
    #        tirsConnected.add((srcTir, dstTir))
    #
    #    clkPeriod: SchedTime = self.netlist.normalizedClkPeriod
    #    dstUseClkI = start_clk(dstTir.timeOffset, clkPeriod)
    #    if srcTir.timeOffset is INVARIANT_TIME:
    #        dstTir.valuesInTime[0].data(srcTir.valuesInTime[0].data)
    #        return
    #
    #    srcStartClkI = start_clk(srcTir.timeOffset, clkPeriod)
    #    assert srcTir is not dstTir, (o, srcTir)
    #    srcOff = dstUseClkI - srcStartClkI
    #    if srcStartClkI > dstUseClkI:
    #        raise AssertionError(srcStartClkI, dstUseClkI, srcTir.timeOffset, dstTir.timeOffset, clkPeriod, dstTir,
    #                             "Source must be available before first use "
    #                             "because otherwise this should be a backedge instead.", o)
    #
    #    if len(srcTir.valuesInTime) <= srcOff:
    #        if isinstance(srcElm, ArchElementPipeline):
    #            # extend the value register pipeline to get data in time when other element requires it
    #            # potentially also extend the src pipeline
    #            srcElm.extendValidityOfRtlResource(srcTir, dstTir.timeOffset)
    #            # assert len(srcTir.valuesInTime) == srcOff + 1
    #        elif isinstance(srcElm, ArchElementFsm):
    #            assert srcElm.fsm.hasUsedStateForClkI(dstUseClkI), ("Must be the case otherwise the dstElm should already be configured to accept data sooner.",
    #                                                       o, srcElm, "->", dstElm, dstUseClkI)
    #        else:
    #            raise NotImplementedError("Need to add extra buffer between FSMs", srcStartClkI, dstUseClkI, o, srcElm, dstElm)
    #
    #    srcTiri = srcTir.get(dstUseClkI * clkPeriod)
    #    assert not dstTir.valuesInTime[0].data.drivers, ("Forward declaration signal must not have a driver yet.",
    #                                                     dstTir, dstTir.valuesInTime[0].data.drivers)
    #    dstTir.valuesInTime[0].data(srcTiri.data)
    #    self._registerSyncForInterElementConnection(srcTiri, dstTir.valuesInTime[0], syncAdded,
    #                                                elementIndex[srcElm], elementIndex[dstElm],
    #                                                srcElm, dstElm, srcStartClkI, dstUseClkI)
    #
    # dstCon =
    # if isinstance(srcElm, ArchElementFsm):
    #    srcSyncIslands = srcElm.fsm.syncIslands
    # else:
    #    srcSyncIslands = [srcElm.syncIsland]
    #
    # if isinstance(dstElm, ArchElementFsm):
    #    dstSyncIslands = dstElm.fsm.syncIslands
    # else:
    #    dstSyncIslands = [dstElm.syncIsland, ]

    # clkPeriod: SchedTime = self.netlist.normalizedClkPeriod
    # # for every input to every element resolve
    # alreadySynced: Set[HlsNetNodeExplicitSync] = set()
    # for dstSyncIsland in dstSyncIslands:
    #    for io in chain(dstSyncIsland.inputs, dstSyncIsland.outputs):
    #        io: HlsNetNodeExplicitSync
    #        if io in alreadySynced:
    #            continue
    #
    #        if io.extraCond is None and io.skipWhen is None:
    #            # skip if there is nothing to potentially add
    #            continue
    #
    #        if io.scheduledZero // clkPeriod != dstUseClkI:
    #            # skip if the IO is not in this synchronized state/stage
    #            continue
    #
    #        for srcSyncIsland in srcSyncIslands:
    #            if io in dstElm.subNodes and isDrivenFromSyncIsland(io, srcSyncIsland, syncIslands):
    #                # :note: there may be the case when new inter element connection is generated
    #                self._propageteInputDependencyToElement(io.extraCond, dstElm)
    #                self._propageteInputDependencyToElement(io.skipWhen, dstElm)
    #
    #                extraCond, skipWhen = dstElm._copyChannelSyncForElmInput(interElmSync, io)
    #                if extraCond is not None:
    #                    dstCon.io_extraCond[interElmSync] = extraCond
    #                if skipWhen is not None:
    #                    dstCon.io_skipWhen[interElmSync] = skipWhen
    #                alreadySynced.add(io)
    #                break
    #
    # @staticmethod
    # def _copyChannelSyncForElmInput(elm: ArchElement, inputIntf: ArchChannelSync, node: HlsNetNodeExplicitSync):
    #     syncTime = node.scheduledOut[0]
    #     if node.skipWhen is not None:
    #         e: HlsNetNodeOut = node.dependsOn[node.skipWhen.in_i]
    #         skipWhen = elm.rtlAllocHlsNetNodeOutInTime(e, syncTime)
    #         skipWhen = SkipWhenMemberList([skipWhen, ])
    #     else:
    #         skipWhen = None
    #
    #     if node.extraCond is not None:
    #         e: HlsNetNodeOut = node.dependsOn[node.extraCond.in_i]
    #         extraCond = elm.rtlAllocHlsNetNodeOutInTime(e, syncTime)
    #         extraCond = ExtraCondMemberList([(skipWhen, extraCond), ])
    #     else:
    #         extraCond = None
    #
    #    return extraCond, skipWhen
