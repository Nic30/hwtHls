from typing import Union, List, Tuple, Set

from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.allocator.fsmContainer import AllocatorFsmContainer
from hwtHls.allocator.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.allocator.pipelineContainer import AllocatorPipelineContainer
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import start_clk, epsilon
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.pipeline import HlsNetlistAnalysisPassDiscoverPipelines, \
    NetlistPipeline
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from ipCorePackager.constants import INTF_DIRECTION


class HlsAllocator():
    """
    Convert the HlsNetlist to architectural elements and delegate the conversion of elements to RLT.

    :ivar namePrefix: name prefix for debug purposes
    :ivar parentHls: parent HLS context for this allocator
    """

    def __init__(self, parentHls: "HlsPipeline", namePrefix:str="hls_"):
        self.parentHls = parentHls
        self.namePrefix = namePrefix
        self._archElements: List[Union[AllocatorFsmContainer, AllocatorPipelineContainer]] = []

    def _discoverArchElements(self):
        hls = self.parentHls
        fsms: HlsNetlistAnalysisPassDiscoverFsm = hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        pipelines: HlsNetlistAnalysisPassDiscoverPipelines = hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverPipelines)
        onlySingleElem = (len(fsms.fsms) + len(pipelines.pipelines)) == 1
        namePrefix = self.namePrefix
        for i, fsm in enumerate(fsms.fsms):
            fsm: IoFsm
            fsmCont = AllocatorFsmContainer(hls, namePrefix if onlySingleElem else f"{namePrefix:s}fsm{i:d}_", fsm)
            self._archElements.append(fsmCont)

        for i, pipe in enumerate(pipelines.pipelines):
            pipe: NetlistPipeline
            pipeCont = AllocatorPipelineContainer(hls, namePrefix if onlySingleElem else f"{namePrefix:s}pipe{i:d}_", pipe.stages)
            self._archElements.append(pipeCont)
    
    def _getFirstUseTime(self, iea: InterArchElementNodeSharingAnalysis, dstElm: AllocatorArchitecturalElement, o: HlsNetNodeOut):
        clk_period = self.parentHls.clk_period
        useT = iea.firstUseTimeOfOutInElem[(dstElm, o)]
        srcStartClkI = start_clk(o.obj.scheduledOut[o.out_i], clk_period)
        dstUseClkI = start_clk(useT, clk_period)
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
                    useT = closestClockIWithState * clk_period + epsilon
                    iea.firstUseTimeOfOutInElem[(dstElm, o)] = useT
                else:
                    raise NotImplementedError("Need to add extra buffer between FSMs or move value load/store in states", srcStartClkI, dstUseClkI, o, srcElm, dstElm)

        return useT
        
    def _declareInterElemenetBoundarySignals(self, iea: InterArchElementNodeSharingAnalysis):
        # first boundary signals needs to be declared, then the body of fsm/pipeline can be constructed
        # because there is no topological order in how the elements are connected
        clk_period = self.parentHls.clk_period
        seenOutputsConnectedToElm: Set[Tuple[AllocatorArchitecturalElement, HlsNetNodeOut]] = set()
        for o, i in iea.interElemConnections:
            o: HlsNetNodeOut
            i: HlsNetNodeIn
            dstElms = iea.ownerOfInput[i]
            for dstElm in dstElms:
                dstElm: AllocatorArchitecturalElement
                if (dstElm, o) in seenOutputsConnectedToElm or dstElm is iea.ownerOfOutput[o]:
                    continue
                seenOutputsConnectedToElm.add((dstElm, o))
                # declare output and all its synonyms 
                useT = self._getFirstUseTime(iea, dstElm, o)
                synonyms = iea.portSynonyms.get(o, ())
                
                # check if any synonym is already declared
                oRes = None
                for syn in synonyms:
                    synRtl = dstElm.netNodeToRtl.get(syn, None)
                    if synRtl is not None:
                        assert oRes is None or oRes is synRtl, ("All synonyms must have same RTL realization", o, oRes, syn, synRtl)
                        assert start_clk(synRtl.timeOffset, clk_period) == start_clk(useT, clk_period) , (synRtl.timeOffset, useT, syn, o)
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
    
    def _getSrcElm(self, iea: InterArchElementNodeSharingAnalysis, o: HlsNetNodeOut) -> AllocatorArchitecturalElement:
        srcElm = iea.ownerOfOutput.get(o, None)
        if srcElm is None:
            srcElm = iea.ownerOfNode[o.obj]

        return srcElm

    def _getSrcDstsElement(self, iea: InterArchElementNodeSharingAnalysis, o: HlsNetNodeOut, i: HlsNetNodeIn)\
            ->Tuple[AllocatorArchitecturalElement, AllocatorArchitecturalElement]:
        srcElm = self._getSrcElm(iea, o)
        
        dstElm = iea.ownerOfInput.get(i, None)
        if dstElm is None:
            dstElm = iea.ownerOfNode[i.obj]
    
        if isinstance(dstElm, AllocatorArchitecturalElement):
            dstElms = (dstElm,)
        else:
            assert isinstance(dstElm, UniqList), dstElm
            dstElms = dstElm
    
        return srcElm, dstElms
        
    def _finalizeInterElementsConnections(self, iea: InterArchElementNodeSharingAnalysis):
        hls = self.parentHls
        # a set used to avoid adding another sync channel if same is already present
        seenOuts: Set[HlsNetNodeOut] = set()
        for o, _ in iea.interElemConnections:
            srcElm = self._getSrcElm(iea, o)
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
        
        syncAdded: Set[Tuple[int, AllocatorArchitecturalElement, AllocatorArchitecturalElement]] = set()
        tirsConnected: Set[Tuple[TimeIndependentRtlResource, TimeIndependentRtlResource]] = set()
        for o, i in iea.interElemConnections:
            o: HlsNetNodeOut
            i: HlsNetNodeIn
            srcElm, dstElms = self._getSrcDstsElement(iea, o, i)
            for dstElm in dstElms:
                if srcElm is dstElm:
                    continue
                # dst should be already delcared from _declareInterElemenetBoundarySignals       
                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                # src should be already declared form AllocatorArchitecturalElement.allocateDataPath
                srcTir: TimeIndependentRtlResource = srcElm.netNodeToRtl[o]
                if (srcTir, dstTir) in tirsConnected:
                    continue
                else:
                    tirsConnected.add((srcTir, dstTir))

                dstUseClkI = start_clk(dstTir.timeOffset, hls.clk_period)
                srcStartClkI = start_clk(srcTir.timeOffset, hls.clk_period)
                assert srcElm is not dstElm, (i, o, srcElm)
                assert srcTir is not dstTir, (i, o, srcTir)
                assert dstUseClkI >= srcStartClkI
                srcOff = dstUseClkI - srcStartClkI
                assert srcStartClkI <= dstUseClkI
                if len(srcTir.valuesInTime) <= srcOff:
                    if isinstance(srcElm, AllocatorPipelineContainer):
                        # extend the value register pipeline to get data in time when other elemnt requires it
                        # potentially also extend the src pipeline
                        srcElm.extendValidityOfRtlResource(srcTir, dstTir.timeOffset)
                        # assert len(srcTir.valuesInTime) == srcOff + 1  
                    else:
                        raise NotImplementedError("Need to add extra buffer between fsms", srcStartClkI, dstUseClkI, o, srcElm, dstElm)
    
                srcSig = srcTir.get(dstUseClkI * hls.clk_period).data
                assert not dstTir.valuesInTime[0].data.drivers, ("Forward declaration already has a driver", dstTir, dstTir.valuesInTime[0].data.drivers)
                dstTir.valuesInTime[0].data(srcSig)
    
                if (dstUseClkI, srcElm, dstElm) not in syncAdded:
                    interElmSync = HandshakeSync()
                    interElmSync = Interface_without_registration(
                        hls.parentUnit, interElmSync,
                        f"{self.namePrefix}sync_{srcElm.namePrefix}_{dstElm.namePrefix}")
                    srcElm.connectSync(dstUseClkI, interElmSync, INTF_DIRECTION.MASTER)
                    dstElm.connectSync(dstUseClkI, interElmSync, INTF_DIRECTION.SLAVE)
                    syncAdded.add((dstUseClkI, srcElm, dstElm))
        
    def allocate(self):
        """
        Translate scheduled circuit to RTL
        
        Problems:

          1. When resolving logic in clock cycle we do not know about registers which will be constucted later.
             Because we did not seen use of this value yet.
          
          2. If the node spans over multiple clock cycles and some part is not in this arch element
              we do not know about it explicitly from node list.
          
          3. We can not just insert register object because it does not solve nodes spaning multiple clock cycles.
        
        
        * We walk the netlist and discover in which time the value is live (in netlist format the connection could lead to any time)
          and we need to find out in which times we should construct registers and most inportantly in which arch. element we should construct them.

        * For each node which is crossing arch element boundary or spans multiple cycles we also have mark the individual parts for clock cycles
          if the node is crossing arch. elem. boundary we also must ask it to declare its io so the node can be constructed from any 
          arch element.

        * First arch element which sees the node allocates it, the alocation is marked in allocator and happens only once.

        * Each arch element explicitly queries the node for the specific time (and input/output combination if node spans over more arch. elements).
        """
        self._discoverArchElements()
        iea = InterArchElementNodeSharingAnalysis(self.parentHls.clk_period)
        if len(self._archElements) > 1:
            iea._analyzeInterElementsNodeSharing(self._archElements)
            if iea.interElemConnections:
                self._declareInterElemenetBoundarySignals(iea)
            
        for e in self._archElements:
            e.allocateDataPath(iea)

        if iea.interElemConnections:
            self._finalizeInterElementsConnections(iea)

        for e in self._archElements:
            e.allocateSync()

