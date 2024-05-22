from typing import Dict, List, Set

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.archElementUtils import ArchElement_merge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.typingFuture import override


class RtlArchPassArchStructureSimplfy(RtlArchPass):

    @staticmethod
    def findSuccessorsPredecessors(archElements: List[ArchElement]):
        archElmSuccessors: Dict[ArchElement, SetList[ArchElement]] = {}
        archElmPredecessors: Dict[ArchElement, SetList[ArchElement]] = {}
        for archElm in archElements:
            archElmSuccessors[archElm] = SetList()
            archElmPredecessors[archElm] = SetList()

        for dstElm in archElements:
            for dep in dstElm.dependsOn:
                srcElm = dep.obj
                archElmSuccessors[srcElm].append(dstElm)
                archElmPredecessors[dstElm].append(srcElm)

        return archElmPredecessors, archElmSuccessors

    @classmethod
    def isPipelineEndingInElm(cls, archElmPredecessors: Dict[ArchElement, SetList[ArchElement]],
                              archElmSuccessors: Dict[ArchElement, SetList[ArchElement]],
                              cur: ArchElementPipeline, dst: ArchElement, path: List[ArchElementPipeline]):
        if cur is dst:
            return True
        elif not isinstance(cur, ArchElementPipeline):
            return False
        elif len(archElmPredecessors[cur]) != 1:
            return False  # this part can be entered from elsewhere so this is not just a direct path
        elif len(archElmSuccessors[cur]) != 1:
            return False  # this part can lead also to somewhere else so this is not just a direct path
        else:
            path.append(cur)
            return cls.isPipelineEndingInElm(archElmSuccessors, archElmPredecessors, archElmSuccessors[cur][0], dst, path)

    @staticmethod
    def shouldMergePipelineToFsm(src: ArchElementPipeline, dst: ArchElementFsm):
        """
        Check if pipeline fits exactly to FSM states.
        """
        for clkI, nodes in enumerate(src.stages):
            if nodes and not dst.fsm.hasUsedStateForClkI(clkI):
                return False
        return True

    @staticmethod
    def shouldMergePipelineToPipeline(src: ArchElementPipeline, dst: ArchElementPipeline):
        """
        :Attention: This function should be called for connected elements, so it it is not checked that elements are actually connected.

        Check if pipeline is parallel to this and is scheduled to clock cycles contained in this pipeline. 
        """
        # HlsNetNodeReadOrWriteToAnyChannel = (
        #    HlsNetNodeReadForwardedge,
        #    HlsNetNodeWriteForwardedge,
        #    HlsNetNodeReadBackedge,
        #    HlsNetNodeWriteBackedge
        # )
        # HlsNetNodeReadOrWrite = (HlsNetNodeRead, HlsNetNodeWrite)
        dstBegin, dstEnd = dst.getBeginEndClkI()
        for clkI, nodes in enumerate(src.stages):
            if nodes:
                if clkI < dstBegin or dstEnd < clkI:
                    return False

        for nodes in src.stages:
            for node in nodes:
                if isinstance(node, HlsNetNodeReadForwardedge) and node.associatedWrite in dst._subNodes:
                    return False
                elif isinstance(node, HlsNetNodeWriteForwardedge) and node.associatedRead in dst._subNodes:
                    return False
        return True

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        if len(netlist.nodes) <= 1:
            return
        archElmPredecessors, archElmSuccessors = self.findSuccessorsPredecessors(netlist.nodes)
        removed: Set[ArchElement] = set()
        for archElm in netlist.nodes:
            if archElm in removed:
                continue

            if isinstance(archElm, ArchElementFsm):
                for suc in archElmSuccessors[archElm]:
                    if suc is archElm:
                        continue
                    #pipelinePath = []
                    #if self.isPipelineEndingInElm(archElmPredecessors, archElmSuccessors, suc, archElm, pipelinePath):
                    #    raise NotImplementedError()

                    # [todo] move all nodes from this clock cycle to predecessor to have element crossing on clock boundary
                    #   * this requires to update channel control writes and possibly move HlsNetNodeWriteForwardedge and HlsNetNodeReadForwardedge
                    if isinstance(suc, ArchElementPipeline):
                        if self.shouldMergePipelineToFsm(suc, archElm):
                            ArchElement_merge(suc, archElm, archElmPredecessors, archElmSuccessors)
                            removed.add(suc)
                            continue

            if isinstance(archElm, ArchElementPipeline):
                for suc in tuple(archElmSuccessors[archElm]):
                    if suc is archElm:
                        continue
                    if suc in removed:
                        # If suc is removed it should not be in archElmSuccessors dict
                        # but we modifying it during the iteration so we used a copy of values
                        # which may not be up to date
                        continue
                    
                    if isinstance(suc, ArchElementPipeline):
                        if self.shouldMergePipelineToPipeline(suc, archElm):
                            ArchElement_merge(suc, archElm, archElmPredecessors, archElmSuccessors)
                            removed.add(suc)
                            continue

        netlist.filterNodesUsingSet(removed)
