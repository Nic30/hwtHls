from typing import Union, List, Tuple, Set, Optional, Dict

from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.architecture.architecturalElement import AllocatorArchitecturalElement
from hwtHls.architecture.fsmContainer import AllocatorFsmContainer
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis, ValuePathSpecItem
from hwtHls.architecture.pipelineContainer import AllocatorPipelineContainer
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
        self._archElements: List[Union[AllocatorFsmContainer, AllocatorPipelineContainer]] = []
        self._iea: Optional[InterArchElementNodeSharingAnalysis] = None

    def _getArchElmBaseName(self, elm:AllocatorArchitecturalElement) -> str:
        namePrefixLen = len(self.namePrefix)
        return elm.namePrefix[namePrefixLen:]

    def _discoverArchElements(self):
        """
        Query HlsNetlistAnalysisPassDiscoverFsm and HlsNetlistAnalysisPassDiscoverPipelines to search AllocatorArchitecturalElement instances
        in current HlsNetlist.
        """
        netlist = self.netlist
        fsms: HlsNetlistAnalysisPassDiscoverFsm = netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        pipelines: HlsNetlistAnalysisPassDiscoverPipelines = netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverPipelines)
        onlySingleElem = (len(fsms.fsms) + len(pipelines.pipelines)) == 1
        namePrefix = self.namePrefix
        for i, fsm in enumerate(fsms.fsms):
            fsm: IoFsm
            fsmCont = AllocatorFsmContainer(netlist, namePrefix if onlySingleElem else f"{namePrefix:s}fsm{i:d}_", fsm)
            self._archElements.append(fsmCont)

        for i, pipe in enumerate(pipelines.pipelines):
            pipe: NetlistPipeline
            pipeCont = AllocatorPipelineContainer(netlist, namePrefix if onlySingleElem else f"{namePrefix:s}pipe{i:d}_", pipe.stages)
            self._archElements.append(pipeCont)

    def _getFirstUseTime(self, iea: InterArchElementNodeSharingAnalysis, dstElm: AllocatorArchitecturalElement, o: HlsNetNodeOut, i: HlsNetNodeIn):
        clkPeriod = self.netlist.normalizedClkPeriod
        useT = iea.firstUseTimeOfOutInElem[(dstElm, o)]
        srcStartClkI = start_clk(o.obj.scheduledOut[o.out_i], clkPeriod)
        dstUseClkI = start_clk(useT, clkPeriod)
        if isinstance(dstElm, AllocatorFsmContainer):
            assert dstUseClkI in dstElm.clkIToStateI, (dstUseClkI, dstElm.clkIToStateI, o, "Output must be scheduled to some cycle corresponding to fsm state")
        if srcStartClkI != dstUseClkI:
            srcElm: AllocatorArchitecturalElement = iea.ownerOfOutput[o]
            # it is required to add buffers somewhere to latch the value to that time
            # we prefer adding the registers to pipelines because it may result in better performance
            if isinstance(srcElm, AllocatorFsmContainer) and dstUseClkI not in srcElm.clkIToStateI:
                if isinstance(dstElm, AllocatorPipelineContainer):
                    # move first use closer to begin of pipeline or even prepend stages for pipeline to be able to accept the src data when it exists
                    assert srcStartClkI in srcElm.clkIToStateI
                    closestClockIWithState = srcStartClkI
                    for clkI in range(srcStartClkI, dstUseClkI + 1):
                        if clkI in srcElm.clkIToStateI:
                            closestClockIWithState = clkI
                    useT = closestClockIWithState * clkPeriod + self.netlist.scheduler.epsilon
                    iea.firstUseTimeOfOutInElem[(dstElm, o)] = useT
                elif isinstance(dstElm, AllocatorFsmContainer):
                    # Need to add extra buffer between FSMs or move value load/store in states
                    # We add new pipeline to architecture and register this pair to interElemConnections
                    srcBaseName = self._getArchElmBaseName(srcElm)
                    dstBaseName = self._getArchElmBaseName(dstElm)
                    bufferPipelineName = f"{self.namePrefix:s}buffer_{srcBaseName:s}{srcStartClkI}_to_{dstBaseName:s}{dstUseClkI}"
                    p = AllocatorPipelineContainer(self.netlist, bufferPipelineName, [])
                    self._archElements.append(p)
                    iea.explicitPathSpec[(o, i, dstElm)] = [ValuePathSpecItem(p, o.obj.scheduledOut[o.out_i], useT)]
                else:
                    raise NotImplementedError("Propagating the value to element of unknown type", dstElm)

        return useT

    def _addOutputAndAllSynonymsToElement(self, o: HlsNetNodeOut, useT: int, synonyms: UniqList[Union[HlsNetNodeOut, HlsNetNodeIn]], dstElm: AllocatorArchitecturalElement):
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

    def _declareInterElemenetBoundarySignals(self, iea: InterArchElementNodeSharingAnalysis):
        # first boundary signals needs to be declared, then the body of fsm/pipeline can be constructed
        # because there is no topological order in how the elements are connected
        seenOutputsConnectedToElm: Set[Tuple[AllocatorArchitecturalElement, HlsNetNodeOut]] = set()
        for o, i in iea.interElemConnections:
            o: HlsNetNodeOut
            i: HlsNetNodeIn
            srcElm = iea.getSrcElm(o)
            dstElms = iea.ownerOfInput[i]
            for dstElm in dstElms:
                dstElm: AllocatorArchitecturalElement

                if srcElm is dstElm or (dstElm, o) in seenOutputsConnectedToElm:
                    # already instantiated, or does not need explicit instantiation, because the port is directly present in element
                    continue

                seenOutputsConnectedToElm.add((dstElm, o))
                # declare output and all its synonyms
                synonyms = iea.portSynonyms.get(o, ())
                explicitPath = iea.explicitPathSpec.get((o, i, dstElm), None)
                if explicitPath is not None:
                    # we must explicitly pass the value through all elements at specific times
                    # for each element in path add output, input pair and connect them inside of element
                    for elmSpec in explicitPath:
                        elmSpec: ValuePathSpecItem
                        if (dstElm, o) in seenOutputsConnectedToElm:
                            assert not dstElm is iea.ownerOfOutput[o]
                            continue
                        self._addOutputAndAllSynonymsToElement(o, elmSpec.beginTime, synonyms, elmSpec.element)
                        seenOutputsConnectedToElm.add((elmSpec.element, o))

                useT = self._getFirstUseTime(iea, dstElm, o, i)
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

    def _finalizeInterElementsConnections(self, iea: InterArchElementNodeSharingAnalysis):
        self._expandAllOutputSynonymsInElement(iea)
        clkPeriod:int = self.netlist.normalizedClkPeriod
        syncAdded: Dict[Tuple[int, AllocatorArchitecturalElement, AllocatorArchitecturalElement], InterArchElementHandshakeSync] = {}
        tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]] = set()
        elementIndex: Dict[AllocatorArchitecturalElement, int] = {a: i for i, a in enumerate(self._archElements)}

        for o, i in iea.interElemConnections:
            o: HlsNetNodeOut
            i: HlsNetNodeIn
            srcElm, dstElms = iea.getSrcDstsElement(o, i)
            for dstElm in dstElms:
                if srcElm is dstElm:
                    continue
                # dst should be already declared from _declareInterElemenetBoundarySignals
                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                # src should be already declared form AllocatorArchitecturalElement.allocateDataPath
                srcTir: TimeIndependentRtlResource = srcElm.netNodeToRtl[o]
                if (srcTir, dstTir) in tirsConnected:
                    # because the signal may have aliases there may be signals of same value which are sing same TimeIndependentRtlResource
                    continue
                else:
                    tirsConnected.add((srcTir, dstTir))

                explicitPath = iea.explicitPathSpec.get((o, i, dstElm), None)
                if explicitPath is not None:
                    # we must explicitly pass the value through all elements at specific times
                    # for each element in path add output, input pair and connect them inside of element
                    for elmSpec in explicitPath:
                        elmSpec: ValuePathSpecItem
                        raise NotImplementedError("Propagate value in specified element and complete the path.")
                        # if (dstElm, o) in seenOutputsConnectedToElm:
                        #    assert not dstElm is iea.ownerOfOutput[o]
                        #    continue
                        # self._addOutputAndAllSynonymsToElement(o, elmSpec.beginTime, synonyms, elmSpec.element)

                dstUseClkI = start_clk(dstTir.timeOffset, clkPeriod)
                srcStartClkI = start_clk(srcTir.timeOffset, clkPeriod)
                assert srcTir is not dstTir, (i, o, srcTir)
                srcOff = dstUseClkI - srcStartClkI
                assert srcStartClkI <= dstUseClkI, (srcStartClkI, dstUseClkI, "Source must be available before first use "
                                                    "because otherwise this should be a backedge instead.")
                if len(srcTir.valuesInTime) <= srcOff:
                    if isinstance(srcElm, AllocatorPipelineContainer):
                        # extend the value register pipeline to get data in time when other element requires it
                        # potentially also extend the src pipeline
                        srcElm.extendValidityOfRtlResource(srcTir, dstTir.timeOffset)
                        # assert len(srcTir.valuesInTime) == srcOff + 1
                    elif isinstance(srcElm, AllocatorFsmContainer):
                        assert dstUseClkI in srcElm.clkIToStateI, ("Must be the case otherwise the pipeline should already been extended.")
                    else:
                        raise NotImplementedError("Need to add extra buffer between FSMs", srcStartClkI, dstUseClkI, o, srcElm, dstElm)
                
                srcTiri = srcTir.get(dstUseClkI * clkPeriod)
                assert not dstTir.valuesInTime[0].data.drivers, ("Forward declaration signal must not have a driver yet.", dstTir, dstTir.valuesInTime[0].data.drivers)
                srcElm._afterOutputUsed(o)
                dstTir.valuesInTime[0].data(srcTiri.data)
                self._registerSyncForInterElementConnection(srcTiri, dstTir.valuesInTime[0], syncAdded,
                                                            elementIndex[srcElm], elementIndex[dstElm],
                                                            srcElm, dstElm, srcStartClkI, dstUseClkI)

    def _registerSyncForInterElementConnection(self,
                                               srcTiri: TimeIndependentRtlResourceItem, dstTiri: TimeIndependentRtlResourceItem,
                                               syncAdded: Dict[Tuple[int, AllocatorArchitecturalElement, AllocatorArchitecturalElement],
                                                               InterArchElementHandshakeSync],
                                               srcElmIndex:int, dstElmIndex:int,
                                               srcElm: AllocatorArchitecturalElement, dstElm: AllocatorArchitecturalElement,
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
