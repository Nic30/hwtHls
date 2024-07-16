from typing import Tuple, Optional, Dict

from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeFsmStateEn
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, \
    offsetInClockCycle

ArchSyncNodeTy = Tuple[ArchElement, int]


class ArchSyncNodeTerm():

    def __init__(self, node: ArchSyncNodeTy, out: HlsNetNodeOut, name: Optional[str]):
        self.node = node
        self.out = out
        self.name = name

    def __hash__(self):
        return hash((self.node, self.out))

    def __eq__(self, other):
        if not isinstance(other, ArchSyncNodeTerm):
            return False
        else:
            return self.node == other.node and self.out == other.out

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name if self.name else ''} {self.node}, {self.out}>"


class ArchElementTermPropagationCtx():
    """
    An object used to propagate node outputs between ArchElement instances
    """

    def __init__(self,
                 exportedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut],
                 parentDstElm: ArchElement,
                 stageEnForSyncNode: Dict[ArchSyncNodeTy, HlsNetNodeOut]):
        self.exportedPorts = exportedPorts
        self.importedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut] = {}
        self.parentDstElm = parentDstElm
        self.stageEnForSyncNode = stageEnForSyncNode

    def propagate(self, srcNode: ArchSyncNodeTy, out: HlsNetNodeOut, name: str) -> HlsNetNodeOut:
        assert out
        assert out.obj in srcNode[0]._subNodes, (srcNode[0], out, name)
        k = ArchSyncNodeTerm(srcNode, out, name)
        curI = self.importedPorts.get(k)
        if curI is None:
            curE = self.exportedPorts.get(k)
            if curE is None:
                curE = exportPortFromArchElement(srcNode, out, name, self.exportedPorts)
            curI, _ = importPortToArchElement(curE, name, (self.parentDstElm, srcNode[1]))
            self.importedPorts[k] = curI
        return curI

    def propagateFromDstElm(self, dstNode: ArchSyncNodeTy, out: HlsNetNodeOut, name: str, resetTimeToClkWindowBegin=False) -> HlsNetNodeOut:
        srcNode = (self.parentDstElm, dstNode[1])
        k = ArchSyncNodeTerm(srcNode, out, name)
        curE = self.exportedPorts.get(k)
        if curE is None:
            curE = exportPortFromArchElement(srcNode, out, name, self.exportedPorts, resetTimeToClkWindowBegin=resetTimeToClkWindowBegin)
        curI, _ = importPortToArchElement(curE, name, dstNode)
        self.importedPorts[k] = curI
        return curI

    def getStageEn(self, node: ArchSyncNodeTy) -> Optional[HlsNetNodeOut]:
        try:
            return self.stageEnForSyncNode[node]
        except KeyError:
            pass
        elmNode, elmNodeClkI = node
        elmNode: ArchElement
        if isinstance(elmNode, ArchElementPipeline):
            if not any(nodes and clkI < elmNodeClkI for (clkI, nodes) in elmNode.iterStages()):
                return None  # first stage of pipeline

        netlist = elmNode.netlist
        enNode = HlsNetNodeFsmStateEn(netlist)
        enNode.resolveRealization()
        enNode._setScheduleZeroTimeSingleClock(elmNodeClkI * netlist.normalizedClkPeriod)
        elmNode._addNodeIntoScheduled(elmNodeClkI, enNode)
        en = self.propagate(node, enNode._outputs[0], f"stateEn_{elmNode._id:d}_{elmNodeClkI:d}")
        self.stageEnForSyncNode[node] = en
        return en


def exportPortFromArchElement(srcNode: ArchSyncNodeTy, out: HlsNetNodeOut, name: str,
                              exportedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut],
                              resetTimeToClkWindowBegin=False):
    cacheKey = ArchSyncNodeTerm(srcNode, out, name)
    cur = exportedPorts.get(cacheKey, None)
    if cur is not None:
        return cur  # this port was already exported, reuse it

    elmNode: ArchElement = srcNode[0]

    assert out.obj.scheduledOut is not None, ("Port must be scheduled", out)
    clkPeriod = elmNode.netlist.normalizedClkPeriod
    # to assert that the port is not exported in sooner time
    time = srcNode[1] * clkPeriod
    if not resetTimeToClkWindowBegin:
        time = max(time, out.obj.scheduledOut[out.out_i])
    _out, interOutNode = elmNode._addOutput(out._dtype, name, time=time)
    link_hls_nodes(out, interOutNode)
    exportedPorts[cacheKey] = _out
    return _out


def importPortToArchElement(out: HlsNetNodeOut, name: str,
                            dstSyncNode: ArchSyncNodeTy) -> Tuple[HlsNetNodeOut, SchedTime]:
    srcArchElm: ArchElement = out.obj
    assert isinstance(srcArchElm, ArchElement), ("Only ports of ArchElement instances should be imported", out)
    clkPeriod = srcArchElm.netlist.normalizedClkPeriod
    srcClkI = indexOfClkPeriod(srcArchElm.scheduledOut[out.out_i], clkPeriod)

    time = srcArchElm.scheduledOut[out.out_i]
    if (srcArchElm, srcClkI) is dstSyncNode:
        # use output already defined inside
        # :note: we must also check for same srcClkI because
        #     we need the value from register in that specific stage,
        #     if we reuse value in a different time we may be using
        #     a different register holding value for that specific stage
        return srcArchElm._outputsInside[out.out_i].dependsOn[0], time

    # propagate port value to inside of syncNode
    dstClkIndex: int = dstSyncNode[1]
    dstTime: int = dstClkIndex * clkPeriod + offsetInClockCycle(time, clkPeriod)
    outer, intern = dstSyncNode[0]._addInput(out._dtype, name, time=dstTime)
    link_hls_nodes(out, outer, checkCycleFree=False)
    return intern, dstTime
