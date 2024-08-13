from typing import Dict, List, Set

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.netlist.builder import HlsNetlistBuilder
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.archElementUtils import ArchElement_merge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, unlink_hls_nodes,\
    unlink_hls_node_input_if_exists
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class RtlArchPassArchStructureSimplify(HlsArchPass):

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

    def _tryRemoveElementIfEmpty(self, archElm: ArchElement):
        for n in archElm._subNodes:
            if not isinstance(n, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut, HlsNetNodeConst)):
                return False
        clkPeriod = archElm.netlist.normalizedClkPeriod
        builder: HlsNetlistBuilder = archElm.netlist.builder
        for o, oi in zip(archElm._outputs, archElm._outputsInside):
            o: HlsNetNodeOut
            oi: HlsNetNodeAggregatePortOut
            src = oi.dependsOn[0]
            while isinstance(src.obj, HlsNetNodeAggregatePortIn):
                raise NotImplementedError()
            if isinstance(src.obj, HlsNetNodeConst):
                srcUsers = src.obj.usedBy[src.out_i]
                for last, u in iter_with_last(archElm.usedBy[o.out_i]):
                    userElm: ArchElement = u.obj
                    assert userElm is not archElm, u
                    if last and len(srcUsers) == 1:
                        unlink_hls_nodes(src, srcUsers[0]) # [todo] src may not be the direct driver of u
                        # move constant nodes between arch elements
                        if src.obj.scheduledIn is not None:
                            clkI = indexOfClkPeriod(src.obj.scheduledZero, clkPeriod)
                            userElm._addNodeIntoScheduled(clkI, src.obj)
                        else:
                            userElm._subNodes.append(src.obj)

                        builder.replaceOutput(userElm._inputsInside[u.in_i]._outputs[0], src, False)
                        userElm._removeInput(u.in_i)
                    else:
                        # duplicate constant in user ArchElement
                        raise NotImplementedError(archElm, u, src)

        for i, dep in zip(archElm._inputs, archElm.dependsOn):
            unlink_hls_nodes(dep, i)
        return True

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        if len(netlist.nodes) <= 1:
            return PreservedAnalysisSet.preserveAll()
        archElmPredecessors, archElmSuccessors = self.findSuccessorsPredecessors(netlist.nodes)
        removed: Set[ArchElement] = set()
        for archElm in netlist.nodes:
            archElm: ArchElement
            if archElm in removed:
                continue

            if self._tryRemoveElementIfEmpty(archElm):
                removed.add(archElm)
                continue

            if isinstance(archElm, ArchElementFsm):
                for suc in archElmSuccessors[archElm]:
                    if suc is archElm:
                        continue
                    # pipelinePath = []
                    # if self.isPipelineEndingInElm(archElmPredecessors, archElmSuccessors, suc, archElm, pipelinePath):
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

        if removed:
            netlist.filterNodesUsingSet(removed)
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
