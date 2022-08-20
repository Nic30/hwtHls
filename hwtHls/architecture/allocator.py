from typing import Union, List, Tuple, Set, Optional, Dict

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis, ValuePathSpecItem
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.pipeline import HlsNetlistAnalysisPassDiscoverPipelines, \
    NetlistPipeline
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
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str="hls_"):
        self.netlist = netlist
        self.namePrefix = namePrefix
        self._archElements: List[Union[ArchElementFsm, ArchElementPipeline]] = []
        self._iea: Optional[InterArchElementNodeSharingAnalysis] = None

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
            pipeCont = ArchElementPipeline(netlist, namePrefix if onlySingleElem else f"{namePrefix:s}pipe{i:d}_", pipe.stages)
            self._archElements.append(pipeCont)

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
                        newUseT = max(clkT + epsilon, useT)
                        iea.firstUseTimeOfOutInElem[(dstElm, o)] = newUseT
                        assert newUseT <= useT, (useT, newUseT, o)
                        return newUseT
                        
                    else:
                        # if dst and src FSM does not overlap at all we must create a buffer
                        # [todo] however we must write to this channel only conditionaly, if it is sure that the CFG will not avoid successor elements
                        # Need to add extra buffer between FSMs or move value load/store in states
                        # We add new pipeline to architecture and register this pair to interElemConnections
                        k = (srcElm, srcStartClkI, dstElm, dstUseClkI)
                        p = interElementBufferPipelines.get(k, None)
                        if p is None:
                            # [todo] this can be used only if there is a common predecessor to multiple arch elements
                            #        and we want to spare resources
                            #        it can not be used only if the consumption of this data is un-coditional
                            #        * This is required because we distibuted CFG to multiple arch elements and once we send
                            #          data to the element the data must also be consummed in order to avoid deadlock
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
                        self._addOutputAndAllSynonymsToElement(o, defT, synonyms, p)
                    
                else:
                    raise NotImplementedError("Propagating the value to element of unknown type", dstElm)

        return useT

    def _addOutputAndAllSynonymsToElement(self, o: HlsNetNodeOut, useT: int,
                                          synonyms: UniqList[Union[HlsNetNodeOut, HlsNetNodeIn]],
                                          dstElm: ArchElement):
        # check if any synonym is already declared
        oRes = None
        for syn in synonyms:
            synRtl = dstElm.netNodeToRtl.get(syn, None)
            if synRtl is not None:
                assert oRes is None or oRes is synRtl, ("All synonyms must have same RTL realization", o, oRes, syn, synRtl)
                assert start_clk(synRtl.timeOffset, self.netlist.normalizedClkPeriod) == start_clk(useT, self.netlist.normalizedClkPeriod) , (synRtl.timeOffset, useT, syn, o)
                oRes = synRtl

        # now optionally declare and set all synonyms at input of dstElm
        if oRes is None:
            # if no synonym declared create a new declaration
            oRes = o.obj.allocateRtlInstanceOutDeclr(dstElm, o, useT)
            for syn in synonyms:
                dstElm.netNodeToRtl[syn] = oRes
        else:
            # declare also rest of the synonyms
            for syn in synonyms:
                synRtl = dstElm.netNodeToRtl.get(syn, None)
                if synRtl is None:
                    dstElm.netNodeToRtl[o] = oRes

    def declareInterElemenetBoundarySignals(self, iea: InterArchElementNodeSharingAnalysis):
        """
        Boundary signals needs to be declared before body of fsm/pipeline is constructed
        because there is no topological order in how the elements are connected.
        """
        seenOutputsConnectedToElm: Set[Tuple[ArchElement, HlsNetNodeOut]] = set()
        interElementBufferPipelines: Dict[Tuple[ArchElement, int, ArchElement, int], ArchElementPipeline] = {}
        for o, i in iea.interElemConnections:
            o: HlsNetNodeOut
            i: HlsNetNodeIn
            srcElm = iea.getSrcElm(o)
            dstElms = iea.ownerOfInput[i]
            for dstElm in dstElms:
                dstElm: ArchElement

                if srcElm is dstElm or (dstElm, o) in seenOutputsConnectedToElm:
                    # already instantiated, or does not need explicit instantiation, because the port is directly present in element
                    continue

                seenOutputsConnectedToElm.add((dstElm, o))
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
                        self._addOutputAndAllSynonymsToElement(o, elmSpec.beginTime, synonyms, elmSpec.element)

                useT = self._getFirstUseTimeAndHandlePropagation(iea, dstElm, o, i, interElementBufferPipelines)
                self._addOutputAndAllSynonymsToElement(o, useT, synonyms, dstElm)

    def _expandAllOutputSynonymsInElement(self, iea: InterArchElementNodeSharingAnalysis):
        # a set used to avoid adding another sync channel if same if is already present
        seenOuts: Set[HlsNetNodeOut] = set()
        for o, _ in iea.interElemConnections:
            srcElm = iea.getSrcElm(o)
            # expand all synonyms at output of element
            if o in seenOuts:
                continue
            else:
                synonyms = iea.portSynonyms.get(o, ())
                if synonyms:
                    foundRtl = None
                    for syn in synonyms:
                        foundRtl = srcElm.netNodeToRtl.get(syn, None)
                        if foundRtl is not None:
                            break
                    assert foundRtl is not None, "At least some synonym port must be defined"
                    for syn in synonyms:
                        rtl = srcElm.netNodeToRtl.get(syn, None)
                        if rtl is None:
                            srcElm.netNodeToRtl[syn] = foundRtl
                        else:
                            assert rtl is foundRtl, "All synonyms must have same RTL object"
                        seenOuts.add(syn)

                else:
                    seenOuts.add(o)
                    assert o in srcElm.netNodeToRtl

    def finalizeInterElementsConnections(self, iea: InterArchElementNodeSharingAnalysis):
        """
        Resolve a final value when the data will be exchanged between arch. element instances
        """
        self._expandAllOutputSynonymsInElement(iea)
        
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
            interElmSync = InterArchElementHandshakeSync(dstUseClkI, srcElm, dstElm)
            srcBaseName = self._getArchElmBaseName(srcElm)
            dstBaseName = self._getArchElmBaseName(dstElm)
            interElmSync = Interface_without_registration(
                self.netlist.parentUnit, interElmSync,
                f"{self.namePrefix:s}sync_{srcBaseName:s}_{srcStartClkI}clk_to_{dstBaseName:s}_{dstUseClkI}clk")
            srcElm.connectSync(dstUseClkI, interElmSync, INTF_DIRECTION.MASTER)
            dstElm.connectSync(dstUseClkI, interElmSync, INTF_DIRECTION.SLAVE)
            syncAdded[syncCacheKey] = interElmSync
        interElmSync.data.append((srcTiri, dstTiri))
