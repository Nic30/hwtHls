from cmath import inf
from typing import Union, List, Dict, Tuple

from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.allocator.fsmContainer import AllocatorFsmContainer
from hwtHls.allocator.pipelineContainer import AllocatorPipelineContainer
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.pipeline import HlsNetlistAnalysisPassDiscoverPipelines, \
    NetlistPipeline
from hwtHls.netlist.nodes.node import HlsNetNode
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

    def allocate(self):
        """
        Translate scheduled circuit to RTL
        
        Problems:

          1. When resolving logic in clock cycle we do not know about registers which will be constucted later.
             Because we did not seen use of this value yet.
          
          2. If the node spans over multiple clock cycles and some part is not in this arch element
              we do not know about it explicitely from node list.
          
          3. We can not just insert register object because it does not solve nodes spaning multiple clock cycles.
        
        
        * We walk the netlist and discover in which time the value is live (in netlist format the connection could lead to any time)
          and we need to find out in which times we should construct registers and most inportantly in which arch. element we should construct them.

        * For each node which is crossing arch element boundary or spans multiple cycles we also have mark the individual parts for clock cycles
          if the node is crossing arch. elem. boundary we also must ask it to declare its io so the node can be constructed from any 
          arch element.

        * First arch element which sees the node allocates it, the alocation is marked in allocator and happens only once.

        * Each arch element explicitely queries the node for the specific time (and input/output combination if node spans over more arch. elements).
        """
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

        boundaryPorts: UniqList[Tuple[HlsNetNodeOut, HlsNetNodeIn]] = UniqList()
        # [todo] specify which IO exactly if the node is split between multiple arch elements
        multiOwnerNodes: UniqList[HlsNetNode] = UniqList()
        ownerOfNode: Dict[HlsNetNode, List[AllocatorArchitecturalElement]] = {}
        # because output value could be used in element multiple times but we need only the first use
        firstUseTimeOfOutInElem: Dict[Tuple[AllocatorArchitecturalElement, HlsNetNodeOut], float] = {}
        if len(self._archElements) > 1:
            for dstElm in self._archElements:
                # for each input check if value originates from other arch element,
                # if it does and was not been resolved yet, declare it on element of origin and add it for starting time to this element 
 
                dstElm: AllocatorArchitecturalElement
                for n in dstElm.allNodes:
                    n: HlsNetNode
                    ol = ownerOfNode.get(n, None)
                    if ol is None:
                        ol = ownerOfNode[n] = []
                    elif dstElm not in ol:
                        multiOwnerNodes.append(n)

                    ol.append(dstElm)
                    for i, o in zip(n._inputs, n.dependsOn):
                        i: HlsNetNodeIn
                        o: HlsNetNodeOut
                        if o.obj not in dstElm.allNodes:
                            # this input is connected to something outside of this arch. element
                            futKey = (dstElm, o)
                            t = firstUseTimeOfOutInElem.get(futKey, inf)
                            curT = n.scheduledIn[i.in_i]
                            if t > curT:
                                # earlier time of use discovered
                                firstUseTimeOfOutInElem[futKey] = curT
                            boundaryPorts.append((o, i))

            if boundaryPorts:
                # first boundary signals needs to be declared, then the body of fsm/pipeline can be constructed
                # because there is no topological order in how the elements are connected
                for o, i in boundaryPorts:
                    o: HlsNetNodeOut
                    i: HlsNetNodeIn
                    srcElm = ownerOfNode[o.obj]
                    if len(srcElm) > 1:
                        raise NotImplementedError("multiOwnerNode")

                    dstElm = ownerOfNode[i.obj]
                    if len(dstElm) > 1:
                        raise NotImplementedError("multiOwnerNode")
                    srcElm: AllocatorArchitecturalElement = srcElm[0]
                    dstElm: AllocatorArchitecturalElement = dstElm[0]
                    # [todo] How many registers should be in srcElm and dstElm?
                    #        Need to check other uses of the output.
                    #        Copy to dst as soon as possible? or at last as possible if still used  in src.
                    #        As last as possible should result in better sharing.
                    #        As soon as possible may result in better performance on fsm-pipe boundaries.
                    #        If element are not directly connected?
                    #        It could be the case that the value is connected to this block multiple times, we ned to propagate just first value
                    fuT = firstUseTimeOfOutInElem[(dstElm, o)]
                    o.obj.allocateRtlInstanceOutDeclr(dstElm, o, fuT)
            
            if multiOwnerNodes:
                raise NotImplementedError()

        for e in self._archElements:
            e.allocateDataPath()

        if boundaryPorts:
            for o, i in boundaryPorts:
                o: HlsNetNodeOut
                i: HlsNetNodeIn
                srcElm = ownerOfNode[o.obj]
                if len(srcElm) > 1:
                    raise NotImplementedError("multiOwnerNode")

                dstElm = ownerOfNode[i.obj]
                if len(dstElm) > 1:
                    raise NotImplementedError("multiOwnerNode")
                srcElm: AllocatorArchitecturalElement = srcElm[0]
                dstElm: AllocatorArchitecturalElement = dstElm[0]
                srcTir: TimeIndependentRtlResource = srcElm.netNodeToRtl[o]
                dstTir: TimeIndependentRtlResource = dstElm.netNodeToRtl[o]
                srcStartClkI = start_clk(srcTir.timeOffset, hls.clk_period)
                fuClkI = start_clk(dstTir.timeOffset, hls.clk_period)
                assert fuClkI >= srcStartClkI
                srcOff = fuClkI - srcStartClkI
                if srcOff > len(srcTir.valuesInTime):
                    raise NotImplementedError("Need to add extra registers to srcElm")
                dstTir.valuesInTime[0].data(srcTir.valuesInTime[srcOff].data)

                interElmSync = HandshakeSync()
                interElmSync = Interface_without_registration(hls.parentUnit, interElmSync, f"{self.namePrefix}sync_{srcElm.namePrefix}_{dstElm.namePrefix}")
                srcElm.connectSync(fuClkI, interElmSync, INTF_DIRECTION.MASTER)
                dstElm.connectSync(fuClkI, interElmSync, INTF_DIRECTION.SLAVE)

        for e in self._archElements:
            e.allocateSync()

