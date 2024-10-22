from typing import Tuple, Dict, Set

from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.ports import HlsNetNodeIn, HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


SyncCacheKey = Tuple[int, ArchElement, ArchElement]


class HlsArchPassAddImplicitSyncChannels(HlsArchPass):
    """
    Analyze ports of ArchElements and add HlsNetNodeWriteForwardedge/HlsNetNodeReadForwardedge pairs.
    Note that these r/w pairs are only synchronization and do not hold any data.
    """

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx) -> PreservedAnalysisSet:
        syncAdded: Set[SyncCacheKey] = set()
        elementIndex: Dict[ArchElement, int] = {a: i for i, a in enumerate(netlist.subNodes)}
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        changed = False
        for srcElm in netlist.subNodes:
            srcElm: ArchElement
            srcElmIndex = elementIndex[srcElm]
            for o, uses, srcTime in zip(srcElm._outputs, srcElm.usedBy, srcElm.scheduledOut):
                o: HlsNetNodeOut
                if HdlType_isVoid(o._dtype):
                    continue

                srcClkI = start_clk(srcTime, clkPeriod)
                for i in uses:
                    i: HlsNetNodeIn
                    dstElm: ArchElement = i.obj
                    dstElmIndex = elementIndex[dstElm]
                    dstTime = dstElm.scheduledIn[i.in_i]
                    dstClkI = start_clk(dstTime, clkPeriod)
                    assert srcClkI == dstClkI, (o, i, srcTime, dstTime, srcClkI, dstClkI)
                    changed |= self._registerSyncForInterElementConnection(
                        netlist, syncAdded, srcElmIndex, dstElmIndex, srcClkI, o, i)

            changed |= srcElm.addImplicitSyncChannelsInsideOfElm()

        if changed:
            return PreservedAnalysisSet.preserveScheduling()
        else:
            return PreservedAnalysisSet.preserveAll()
        
        
    @classmethod
    def _registerSyncForInterElementConnection(cls,
                                               netlist: HlsNetlistCtx,
                                               syncAdded: Set[SyncCacheKey],
                                               srcElmIndex:int, dstElmIndex:int,
                                               clkIndex:int,
                                               o: HlsNetNodeOut,
                                               i: HlsNetNodeIn,
                                              ):
        """
        :param syncAdded: a dictionary used to track where sync channels were already added
        :param srcElmIndex: index of srcElement in node list
        :param dstElmIndex: index of srcElement in node list
        :note: srcElmIndex, dstElmIndex are used to check for potential channel in opposite direction.
        :param clkIndex: An index of clock period window where i and o are scheduled
        :param o: An output of the ArchElement instance
        :param i: An input of the ArchElement instance which is connected to o
        """
        # use index to resolve edge direction
        # (Because there must be at most one, no matter the direction)
        srcElm: ArchElement = o.obj
        dstElm: ArchElement = i.obj
        if srcElmIndex <= dstElmIndex:
            syncCacheKey = (clkIndex, srcElm, dstElm)
        else:
            syncCacheKey = (clkIndex, dstElm, srcElm)

        if syncCacheKey not in syncAdded:
            # [todo] inject read.ready to extraCond/skipWhen of all successor IO nodes
            clkPeriod: SchedTime = netlist.normalizedClkPeriod
            epsilon: SchedTime = netlist.scheduler.epsilon

            # create new interElmSync channel connecting two elements and realizing the synchronization
            srcBaseName = srcElm._getBaseName()
            dstBaseName = dstElm._getBaseName()

            time = ((clkIndex + 1) * clkPeriod) - epsilon  # at the end of clkIndex

            dummyC = HlsNetNodeConst(netlist, HVoidOrdering.from_py(None))
            dummyC.resolveRealization()
            dummyC._setScheduleZeroTimeSingleClock(time - epsilon)
            srcElm._addNodeIntoScheduled(clkIndex, dummyC)

            name = f"{netlist.namePrefix:s}sync_clk{clkIndex}_{srcBaseName:s}_to_{dstBaseName:s}"
            wNode = HlsNetNodeWriteForwardedge(srcElm.netlist, name=f"{name:s}_atSrc")
            dummyC._outputs[0].connectHlsIn(wNode._portSrc)
            wNode.resolveRealization()
            wNode._setScheduleZeroTimeSingleClock(time)
            srcElm._addNodeIntoScheduled(clkIndex, wNode)

            rNode = HlsNetNodeReadForwardedge(dstElm.netlist, dtype=HVoidOrdering, name=f"{name:s}_atDst")
            rNode.resolveRealization()
            rNode._setScheduleZeroTimeSingleClock(time)
            wNode.associateRead(rNode)
            dstElm._addNodeIntoScheduled(clkIndex, rNode)

            syncAdded.add(syncCacheKey)
            return True

        return False
