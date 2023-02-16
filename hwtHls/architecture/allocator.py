from itertools import chain
from typing import Union, List, Tuple, Set, Optional, Dict

from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.architecture.allocatorUtils import isDrivenFromSyncIsland, \
    expandAllOutputSynonymsInElement, addOutputAndAllSynonymsToElement
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis, ValuePathSpecItem
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.analysis.betweenSyncIslands import HlsNetlistAnalysisPassBetweenSyncIslands
from hwtHls.netlist.analysis.fsms import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.pipelines import HlsNetlistAnalysisPassDiscoverPipelines, \
    NetlistPipeline
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import start_clk
from ipCorePackager.constants import INTF_DIRECTION


class HlsAllocator():
    """
    Convert the HlsNetlist to architectural elements and delegate the conversion of elements to RLT.

    :note: this class contains only methods for allocation which are used by HlsPlatform class to perform the allocation
    :see: :meth:`hwtHls.platform.platform.DefaultHlsPlatform.runRtlNetlistPasses`
    :ivar namePrefix: name prefix for debug purposes
    :ivar netlist: parent HLS context for this allocator
    :ivar seenOutputsConnectedToElm: dictionary of instantiated inter element connections
        the value is a time of appearance of that output in dst element
    :note: seenOutputsConnectedToElm, interElementBufferPipelines are used to remove duplicates
        when instantiating inter element connections
    :ivar _dbgAddNamesToSyncSignals: add names to synchronization signals in order to improve readability,
        dissabled by default as it goes agains optimizations
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str="hls_"):
        self.netlist = netlist
        self.namePrefix = namePrefix
        self._archElements: List[Union[ArchElementFsm, ArchElementPipeline]] = []
        self._iea: Optional[InterArchElementNodeSharingAnalysis] = None
        
        self.seenOutputsConnectedToElm: Dict[Tuple[ArchElement, HlsNetNodeOut], int] = {}
        self.interElementBufferPipelines: Dict[Tuple[ArchElement, int, ArchElement, int], ArchElementPipeline] = {}
        self._dbgAddNamesToSyncSignals = False

    def _getArchElmBaseName(self, elm:ArchElement) -> str:
        namePrefixLen = len(self.namePrefix)
        return elm.namePrefix[namePrefixLen:]

    def _discoverArchElements(self):
        """
        Query HlsNetlistAnalysisPassDiscoverFsm and HlsNetlistAnalysisPassDiscoverPipelines to search ArchElement instances
        in current HlsNetlist.
        """
        netlist = self.netlist
        fsms: HlsNetlistAnalysisPassDiscoverFsm = netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        pipelines: HlsNetlistAnalysisPassDiscoverPipelines = netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverPipelines)
        onlySingleElem = (len(fsms.fsms) + len(pipelines.pipelines)) == 1
        namePrefix = self.namePrefix
        for i, fsm in enumerate(fsms.fsms):
            fsm: IoFsm
            fsmCont = ArchElementFsm(netlist, namePrefix if onlySingleElem else f"{namePrefix:s}fsm{i:d}_", fsm)
            self._archElements.append(fsmCont)

        for i, pipe in enumerate(pipelines.pipelines):
            pipe: NetlistPipeline
            pipeCont = ArchElementPipeline(netlist, namePrefix if onlySingleElem else f"{namePrefix:s}pipe{i:d}_",
                                           pipe.stages, pipe.syncIsland)
            self._archElements.append(pipeCont)

        for elm in self._archElements:
            elm._dbgAddNamesToSyncSignals = self._dbgAddNamesToSyncSignals

    def _getFirstUseTimeAndHandlePropagation(self,
                                             iea: InterArchElementNodeSharingAnalysis,
                                             dstElm: ArchElement,
                                             o: HlsNetNodeOut, i: HlsNetNodeIn,
                                             interElementBufferPipelines: Dict[Tuple[ArchElement, int, ArchElement, int], ArchElementPipeline]):
        clkPeriod = self.netlist.normalizedClkPeriod
        useT = iea.firstUseTimeOfOutInElem[(dstElm, o)]
        srcStartClkI = start_clk(o.obj.scheduledOut[o.out_i], clkPeriod)
        dstUseClkI = start_clk(useT, clkPeriod)
        if isinstance(dstElm, ArchElementFsm):
            assert dstUseClkI in dstElm.fsm.clkIToStateI, (dstUseClkI, dstElm.fsm.clkIToStateI, o, "Output must be scheduled to some cycle corresponding to fsm state")

        if srcStartClkI != dstUseClkI:
            srcElm: ArchElement = iea.ownerOfOutput[o]
            # it is required to add buffers somewhere to latch the value to that time
            # we prefer adding the registers to pipelines because it may result in better performance
            epsilon: int = self.netlist.scheduler.epsilon
            if isinstance(srcElm, ArchElementFsm) and dstUseClkI not in srcElm.fsm.clkIToStateI:
                srcElm: ArchElementFsm
                if isinstance(dstElm, ArchElementPipeline):
                    # extend the life of the variable in FSM if possible
                    # optionally move first use closer to begin of pipeline or even prepend stages for pipeline
                    # to be able to accept the src data when it exists
                    assert srcStartClkI in srcElm.fsm.clkIToStateI
                    closestClockIWithState = srcStartClkI
                    for clkI in range(srcStartClkI, dstUseClkI + 1):
                        if clkI in srcElm.fsm.clkIToStateI:
                            closestClockIWithState = clkI
                    newUseT = closestClockIWithState * clkPeriod + epsilon
                    assert newUseT <= useT, (useT, newUseT, o)
                    iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
                    return newUseT

                elif isinstance(dstElm, ArchElementFsm):
                    dstElm: ArchElementFsm
                    # find overlaps in schedulization of FSMs
                    beginClkI = max(srcElm.fsmBeginClk_i, dstElm.fsmBeginClk_i)
                    endClkI = min(srcElm.fsmEndClk_i, dstElm.fsmEndClk_i)
                    sharedClkI = None
                    if beginClkI > endClkI:
                        # no overlap
                        pass
                    else:
                        for clkI in range(beginClkI, endClkI + 1):
                            if clkI in srcElm.fsm.clkIToStateI and clkI in dstElm.fsm.clkIToStateI:
                                sharedClkI = clkI

                    if sharedClkI is not None:
                        # if src and dst FSM overlaps exactly in 1 time we can safely transfer data there
                        clkT = sharedClkI * clkPeriod
                        assert clkT <= useT, (o, clkT, useT)
                        newUseT = min(clkT + epsilon, useT)
                        iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
                        assert newUseT <= useT, (useT, newUseT, o)
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
                            bufferPipelineName = f"{self.namePrefix:s}buffer_{srcBaseName:s}{srcStartClkI}_to_{dstBaseName:s}{dstUseClkI}"
                            stages = [[] for _ in range(start_clk(useT, clkPeriod) + 1)]
                            p = ArchElementPipeline(self.netlist, bufferPipelineName, stages)
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

        return useT

    def declareInterElemenetBoundarySignals(self, iea: InterArchElementNodeSharingAnalysis):
        """
        Boundary signals needs to be declared before body of fsm/pipeline is constructed
        because there is no topological order in how the elements are connected.
        """
        assert not self.seenOutputsConnectedToElm
        assert not self.interElementBufferPipelines
        for o, i in iea.interElemConnections:
            srcElm = iea.getSrcElm(o)
            dstElms = iea.ownerOfInput[i]
            for dstElm in dstElms:
                dstElm: ArchElement
                self._declareInterElemenetBoundarySignal(iea, o, i, srcElm, dstElm)
        
    def _declareInterElemenetBoundarySignal(self, iea: InterArchElementNodeSharingAnalysis,
                                           o: HlsNetNodeOut,
                                           i: HlsNetNodeIn,
                                           srcElm: ArchElement, dstElm: ArchElement):
        seenOutputsConnectedToElm = self.seenOutputsConnectedToElm
        if srcElm is dstElm:
            # the data in same element is not an inter-element connection
            return
        seenKey = (dstElm, o)
        prevUseTime = seenOutputsConnectedToElm.get(seenKey, None)
        if prevUseTime is not None and prevUseTime <= iea.firstUseTimeOfOutInElem[seenKey]:
            # already instantiated, or does not need explicit instantiation, because the port is directly present in element
            return

        # declare output and all its synonyms
        synonyms = iea.portSynonyms.get(o, ())
        explicitPath = iea.explicitPathSpec.get((o, i, dstElm), None)
        if explicitPath is not None:
            for elmSpec in explicitPath:
                elmSpec: ValuePathSpecItem
                if (elmSpec.element, o) in seenOutputsConnectedToElm:
                    assert not elmSpec.element is iea.ownerOfOutput[o]
                    continue
                seenOutputsConnectedToElm.add((elmSpec.element, o))
                addOutputAndAllSynonymsToElement(o, elmSpec.beginTime, synonyms, elmSpec.element, self.netlist.normalizedClkPeriod)

        useT = self._getFirstUseTimeAndHandlePropagation(iea, dstElm, o, i, self.interElementBufferPipelines)
        seenOutputsConnectedToElm[seenKey] = useT
        addOutputAndAllSynonymsToElement(o, useT, synonyms, dstElm, self.netlist.normalizedClkPeriod)

    def finalizeInterElementsConnections(self, iea: InterArchElementNodeSharingAnalysis):
        """
        Resolve a final value when the data will be exchanged between arch. element instances
        """
        expandAllOutputSynonymsInElement(iea)
        
        SyncCacheKey = Tuple[int, ArchElement, ArchElement]
        syncAdded: Dict[SyncCacheKey, InterArchElementHandshakeSync] = {}
        tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]] = set()
        elementIndex: Dict[ArchElement, int] = {a: i for i, a in enumerate(self._archElements)}

        for o, i in iea.interElemConnections:
            o: HlsNetNodeOut
            i: HlsNetNodeIn
            srcElm, dstElms = iea.getSrcDstsElement(o, i)
            for dstElm in dstElms:
                if srcElm is dstElm:
                    # data passed internally in the element
                    continue

                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                if dstTir.valuesInTime[0].data.drivers:
                    # the value is already propagated to dstElm
                    continue

                # src should be already declared form ArchElement.allocateDataPath or declareInterElemenetBoundarySignals
                srcTir: TimeIndependentRtlResource = srcElm.netNodeToRtl[o]
                explicitPath = iea.explicitPathSpec.get((o, i, dstElm), None)
                if explicitPath is not None:
                    # we must explicitly pass the value through all elements at specific times
                    # for each element in path add output, input pair and connect them inside of element
                    # synonyms = iea.portSynonyms.get(o, ())
                    for elmSpec in explicitPath:
                        elmSpec: ValuePathSpecItem
                        _dstElm = elmSpec.element
                        dstTir: TimeIndependentRtlResource = _dstElm.netNodeToRtl[o]
                        self._finalizeInterElementsConnection(o, srcTir, dstTir, srcElm, _dstElm,
                                                              elementIndex, syncAdded, tirsConnected)
                        _dstElm.extendValidityOfRtlResource(dstTir, elmSpec.endTime)
                        srcTir = dstTir
                        srcElm = _dstElm

                # dst should be already declared from declareInterElemenetBoundarySignals
                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                self._finalizeInterElementsConnection(o, srcTir, dstTir, srcElm, dstElm, elementIndex, syncAdded, tirsConnected)

    def _finalizeInterElementsConnection(self, o: HlsNetNodeOut,
                                         srcTir: TimeIndependentRtlResource, dstTir: TimeIndependentRtlResource,
                                         srcElm: ArchElement, dstElm: ArchElement,
                                         elementIndex: Dict[ArchElement, int],
                                         syncAdded: Dict[Tuple[int, ArchElement, ArchElement],
                                                         InterArchElementHandshakeSync],
                                         tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]]):
        if (srcTir, dstTir) in tirsConnected:
            # because the signal may have aliases there may be signals of same value which are sing same TimeIndependentRtlResource
            return
        else:
            tirsConnected.add((srcTir, dstTir))

        clkPeriod: int = self.netlist.normalizedClkPeriod
        dstUseClkI = start_clk(dstTir.timeOffset, clkPeriod)
        if srcTir.timeOffset is INVARIANT_TIME:
            dstTir.valuesInTime[0].data(srcTir.valuesInTime[0].data)
            return

        srcStartClkI = start_clk(srcTir.timeOffset, clkPeriod)
        assert srcTir is not dstTir, (o, srcTir)
        srcOff = dstUseClkI - srcStartClkI
        assert srcStartClkI <= dstUseClkI, (srcStartClkI, dstUseClkI, "Source must be available before first use "
                                            "because otherwise this should be a backedge instead.")
        if len(srcTir.valuesInTime) <= srcOff:
            if isinstance(srcElm, ArchElementPipeline):
                # extend the value register pipeline to get data in time when other element requires it
                # potentially also extend the src pipeline
                srcElm.extendValidityOfRtlResource(srcTir, dstTir.timeOffset)
                # assert len(srcTir.valuesInTime) == srcOff + 1
            elif isinstance(srcElm, ArchElementFsm):
                assert dstUseClkI in srcElm.fsm.clkIToStateI, ("Must be the case otherwise the dstElm should already be configured to accept data sooner.",
                                                           o, srcElm, "->", dstElm, srcElm.fsm.clkIToStateI, "->", dstUseClkI)
            else:
                raise NotImplementedError("Need to add extra buffer between FSMs", srcStartClkI, dstUseClkI, o, srcElm, dstElm)
        
        srcTiri = srcTir.get(dstUseClkI * clkPeriod)
        assert not dstTir.valuesInTime[0].data.drivers, ("Forward declaration signal must not have a driver yet.",
                                                         dstTir, dstTir.valuesInTime[0].data.drivers)
        srcElm._afterOutputUsed(o)
        dstTir.valuesInTime[0].data(srcTiri.data)
        self._registerSyncForInterElementConnection(srcTiri, dstTir.valuesInTime[0], syncAdded,
                                                    elementIndex[srcElm], elementIndex[dstElm],
                                                    srcElm, dstElm, srcStartClkI, dstUseClkI)

    def _propageteInputDependencyToElement(self, i: Optional[HlsNetNodeIn], dstElm: ArchElement):
        if i is None:
            return
        dep = i.obj.dependsOn[i.in_i]
        iea = self._iea
        srcElm = iea.ownerOfOutput[dep]
        if srcElm is dstElm:
            return
        else:
            useKey = (dstElm, dep)
            useTime = iea.firstUseTimeOfOutInElem.get(useKey, None)
            thisUseTime = i.obj.scheduledIn[i.in_i]
            if useTime is None:
                useTime = thisUseTime
            else:
                useTime = min(useTime, thisUseTime)
            iea.firstUseTimeOfOutInElem[useKey] = useTime
            self._declareInterElemenetBoundarySignal(self._iea, dep, i, srcElm, dstElm)
            dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[dep]
            if thisUseTime < dstTir.timeOffset:
                raise NotImplementedError(dep, i, thisUseTime, dstTir.timeOffset)
            
    def _registerSyncForInterElementConnection(self,
                                               srcTiri: TimeIndependentRtlResourceItem, dstTiri: TimeIndependentRtlResourceItem,
                                               syncAdded: Dict[Tuple[int, ArchElement, ArchElement],
                                                               InterArchElementHandshakeSync],
                                               srcElmIndex:int, dstElmIndex:int,
                                               srcElm: ArchElement, dstElm: ArchElement,
                                               srcStartClkI:int, dstUseClkI:int):
        if srcElmIndex > dstElmIndex:
            syncCacheKey = (dstUseClkI, dstElm, srcElm)
        else:
            syncCacheKey = (dstUseClkI, srcElm, dstElm)
        
        interElmSync = syncAdded.get(syncCacheKey, None)
        if interElmSync is None:
            # create new interElmSync channel connecting two elements and realizing the synchronization
            # syncIslands: HlsNetlistAnalysisPassBetweenSyncIslands = self.netlist.getAnalysis(HlsNetlistAnalysisPassBetweenSyncIslands)
            interElmSync = InterArchElementHandshakeSync(dstUseClkI, srcElm, dstElm)
            srcBaseName = self._getArchElmBaseName(srcElm)
            dstBaseName = self._getArchElmBaseName(dstElm)
            interElmSync = Interface_without_registration(
                self.netlist.parentUnit, interElmSync,
                f"{self.namePrefix:s}sync_{srcBaseName:s}_clk{srcStartClkI}_to_{dstBaseName:s}_clk{dstUseClkI}")
            srcElm.connectSync(dstUseClkI, interElmSync, INTF_DIRECTION.MASTER, True)
            dstCon = dstElm.connectSync(dstUseClkI, interElmSync, INTF_DIRECTION.SLAVE, True)
            
            # if isinstance(srcElm, ArchElementFsm):
            #    srcSyncIslands = srcElm.fsm.syncIslands
            # else:
            #    srcSyncIslands = [srcElm.syncIsland]
            #
            # if isinstance(dstElm, ArchElementFsm):
            #    dstSyncIslands = dstElm.fsm.syncIslands
            # else:
            #    dstSyncIslands = [dstElm.syncIsland, ]
            
            # clkPeriod: int = self.netlist.normalizedClkPeriod
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
            #            if io in dstElm.allNodes and isDrivenFromSyncIsland(io, srcSyncIsland, syncIslands):
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
            syncAdded[syncCacheKey] = interElmSync

        interElmSync.data.append((srcTiri, dstTiri))
