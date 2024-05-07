from typing import Tuple, Dict, Set

from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    INVARIANT_TIME
from hwtHls.architecture.transformation.addImplicitSyncChannels import SyncCacheKey
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage


class RtlArchPassMoveArchElementPortsToMinimizeSync(RtlArchPass):
    """
    This pass reschedules ArchElement ports to minimize number of clock cycles where the data is exchanged between elements.
    For example, a value is passes to other element once it is required in there.
    However the value may be potentially transfered sooner with other data and synchronization in that cycle may be avoided.
    There are several cases where it is beneficial to modify time when data is moved described in this code.
    """

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        raise NotImplementedError()

    def _handleInterArchElementPropagation(self, o: HlsNetNodeOut, i: HlsNetNodeIn):
        clkPeriod = self.netlist.normalizedClkPeriod
        dstElm: ArchElement = i.obj
        useT = dstElm.scheduledIn[i.in_i]
        defTime = o.obj.scheduledOut[o.out_i]
        assert defTime <= useT, (defTime, useT, o)
        srcStartClkI = start_clk(defTime, clkPeriod)
        dstUseClkI = start_clk(useT, clkPeriod)
        if isinstance(dstElm, ArchElementFsm):
            assert dstElm.fsm.hasUsedStateForClkI(dstUseClkI), (
                dstUseClkI, o, "Output must be scheduled to some cycle corresponding to fsm state")

        if srcStartClkI != dstUseClkI:
            srcElm: ArchElement = o.obj
            # it is required to add buffers somewhere to latch the value to that time
            # we prefer adding the registers to pipelines because it may result in better performance
            epsilon: int = self.netlist.scheduler.epsilon
            if isinstance(srcElm, ArchElementFsm) and not srcElm.fsm.hasUsedStateForClkI(dstUseClkI):
                srcElm: ArchElementFsm
                if isinstance(dstElm, ArchElementPipeline):
                    # extend the life of the variable in FSM if possible
                    # optionally move first use closer to begin of pipeline or even prepend stages for pipeline
                    # to be able to accept the src data when it exists
                    assert srcElm.fsm.hasUsedStateForClkI(srcStartClkI), (srcElm, srcStartClkI)
                    closestClockIWithState = srcStartClkI
                    for clkI in range(srcStartClkI, dstUseClkI + 1):
                        if srcElm.fsm.states[clkI]:
                            closestClockIWithState = clkI
                    newUseT = closestClockIWithState * clkPeriod + epsilon
                    assert newUseT <= useT, (useT, newUseT, o)
                    assert defTime <= newUseT, (defTime, newUseT, o)
                    iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
                    return newUseT

                elif isinstance(dstElm, ArchElementFsm):
                    dstElm: ArchElementFsm
                    # find overlaps in schedulization of FSMs
                    beginClkI = max(srcElm._beginClkI, dstElm._beginClkI)
                    endClkI = min(srcElm._endClkI, dstElm._endClkI)
                    sharedClkI = None
                    if beginClkI > endClkI:
                        # no overlap
                        pass
                    else:
                        for clkI in range(beginClkI, endClkI + 1):
                            if clkI * clkPeriod > defTime and srcElm.fsm.hasUsedStateForClkI(clkI) and dstElm.fsm.hasUsedStateForClkI(clkI):
                                sharedClkI = clkI
                                break

                    if sharedClkI is not None:
                        # if src and dst FSM overlaps exactly in 1 time we can safely transfer data there
                        clkT = sharedClkI * clkPeriod
                        assert clkT <= useT, (o, clkT, useT)
                        newUseT = min(clkT + epsilon, useT)
                        iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
                        assert newUseT <= useT, (useT, newUseT, o)
                        assert defTime <= newUseT, (defTime, newUseT, o)
                        return newUseT

                    else:
                        # if dst and src FSM does not overlap at all we must create a buffer
                        # [todo] however we must write to this channel only conditionally, if it is sure that the CFG will not avoid successor elements
                        # Need to add extra buffer between FSMs or move value load/store in states
                        # We add new pipeline to architecture and register this pair to interElemConnections
                        k = (srcElm, srcStartClkI, dstElm, dstUseClkI)
                        p = interElementBufferPipelines.get(k, None)
                        if p is None:
                            # [todo] this can be used only if there is a common predecessor to multiple arch elements
                            #        and we want to spare resources
                            #        it can not be used only if the consumption of this data is unconditional
                            #        * This is required because we distributed CFG to multiple arch elements and once we send
                            #          data to the element the data must also be consumed in order to avoid deadlock
                            srcBaseName = self._getArchElmBaseName(srcElm)
                            dstBaseName = self._getArchElmBaseName(dstElm)
                            bufferPipelineName = f"{self.name:s}buffer_{srcBaseName:s}{srcStartClkI}_to_{dstBaseName:s}{dstUseClkI}"
                            stages = [[] for _ in range(start_clk(useT, clkPeriod) + 1)]
                            p = ArchElementPipeline(self.netlist, bufferPipelineName, stages, None)
                            self._archElements.append(p)
                            interElementBufferPipelines[k] = p

                        # [todo] if src is ArchElementFsm it may be possible (if it is guaranteed that the register will not be written)
                        #        to extend register life to shorten the buffer
                        # [todo] it may be possible to move value to dstElm sooner if CFG and scheduling allows this
                        synonyms = iea.portSynonyms.get(o, ())
                        defT = o.obj.scheduledOut[o.out_i]
                        iea.explicitPathSpec[(o, i, dstElm)] = [ValuePathSpecItem(p, defT, useT), ]
                        iea.firstUseTimeOfOutInElem[(p, o)] = defT
                        addOutputAndAllSynonymsToElement(o, defT, synonyms, p, self.netlist.normalizedClkPeriod)

                else:
                    raise NotImplementedError("Propagating the value to element of unknown type", dstElm)

    def extendValidityOfRtlResource(self, tir: TimeIndependentRtlResource, endTime: float):
        assert self._rtlDatapathAllocated
        assert not self._rtlSyncAllocated
        assert tir.timeOffset is not INVARIANT_TIME
        assert endTime > tir.timeOffset, (tir, tir.timeOffset, endTime)

        clkPeriod = self.netlist.normalizedClkPeriod
        t = tir.timeOffset + (len(tir.valuesInTime) - 1) * clkPeriod + self.netlist.scheduler.epsilon
        assert t < endTime
        # :note: done in reverse so we do not have to always iterate over registered prequel
        while t <= endTime:
            t += clkPeriod
            i = int(t // clkPeriod)
            if i >= len(self.connections):
                self.stages.append([])
                self.connections.append(ConnectionsOfStage(self, i))

            sigs = self.connections.getForClkIndex(i).signals
            assert tir not in sigs
            tir.get(t)
            sigs.append(tir)

    def finalizeInterElementsConnections(self):
        """
        Resolve a final value when the data will be exchanged between arch. element instances
        """

        syncAdded: Set[SyncCacheKey] = {}
        tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]] = set()
        elementIndex: Dict[ArchElement, int] = {a: i for i, a in enumerate(self.netlist.nodes)}
        for srcElm in self.netlist.nodes:
            srcElm: ArchElement
            for o, uses in zip(srcElm._outputs, srcElm.usedBy):
                o: HlsNetNodeOut
                if HdlType_isVoid(o._dtype):
                    continue
                for i in uses:
                    i: HlsNetNodeIn
                    dstElm = i.obj
                    dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                    if dstTir.valuesInTime[0].data.drivers:
                        # the value is already propagated to dstElm
                        continue

                    # src should be already declared form ArchElement.rtlAllocDatapath or declareInterElemenetBoundarySignals
                    srcTir: TimeIndependentRtlResource = srcElm.netNodeToRtl[o]
                    # dst should be already declared from declareInterElemenetBoundarySignals
                    dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                    self._finalizeInterElementsConnection(o, srcTir, dstTir, srcElm, dstElm, elementIndex, syncAdded, tirsConnected)

    def _finalizeInterElementsConnection(self, o: HlsNetNodeOut,
                                         srcTir: TimeIndependentRtlResource, dstTir: TimeIndependentRtlResource,
                                         srcElm: ArchElement, dstElm: ArchElement,
                                         elementIndex: Dict[ArchElement, int],
                                         syncAdded: Set[SyncCacheKey],
                                         tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]]):
        if (srcTir, dstTir) in tirsConnected:
            # because the signal may have aliases there may be signals of same value which are sing same TimeIndependentRtlResource
            return
        else:
            tirsConnected.add((srcTir, dstTir))

        clkPeriod: SchedTime = self.netlist.normalizedClkPeriod
        dstUseClkI = start_clk(dstTir.timeOffset, clkPeriod)
        if srcTir.timeOffset is INVARIANT_TIME:
            dstTir.valuesInTime[0].data(srcTir.valuesInTime[0].data)
            return

        srcStartClkI = start_clk(srcTir.timeOffset, clkPeriod)
        assert srcTir is not dstTir, (o, srcTir)
        srcOff = dstUseClkI - srcStartClkI
        if srcStartClkI > dstUseClkI:
            raise AssertionError(srcStartClkI, dstUseClkI, srcTir.timeOffset, dstTir.timeOffset, clkPeriod, dstTir,
                                 "Source must be available before first use "
                                 "because otherwise this should be a backedge instead.", o)

        if len(srcTir.valuesInTime) <= srcOff:
            if isinstance(srcElm, ArchElementPipeline):
                # extend the value register pipeline to get data in time when other element requires it
                # potentially also extend the src pipeline
                srcElm.extendValidityOfRtlResource(srcTir, dstTir.timeOffset)
                # assert len(srcTir.valuesInTime) == srcOff + 1
            elif isinstance(srcElm, ArchElementFsm):
                assert srcElm.fsm.hasUsedStateForClkI(dstUseClkI), ("Must be the case otherwise the dstElm should already be configured to accept data sooner.",
                                                           o, srcElm, "->", dstElm, dstUseClkI)
            else:
                raise NotImplementedError("Need to add extra buffer between FSMs", srcStartClkI, dstUseClkI, o, srcElm, dstElm)

        srcTiri = srcTir.get(dstUseClkI * clkPeriod)
        assert not dstTir.valuesInTime[0].data.drivers, ("Forward declaration signal must not have a driver yet.",
                                                         dstTir, dstTir.valuesInTime[0].data.drivers)
        dstTir.valuesInTime[0].data(srcTiri.data)
        self._registerSyncForInterElementConnection(srcTiri, dstTir.valuesInTime[0], syncAdded,
                                                    elementIndex[srcElm], elementIndex[dstElm],
                                                    srcElm, dstElm, srcStartClkI, dstUseClkI)

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
    #            if io in dstElm._subNodes and isDrivenFromSyncIsland(io, srcSyncIsland, syncIslands):
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
        return extraCond, skipWhen