from typing import Tuple, Optional, Dict

from hwt.hdl.operatorDefs import HwtOps
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.architecture.transformation.utils.dummyScheduling import scheduleUnscheduledControlLogic
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate, \
    HlsNetNodeAggregatePortOut, HlsNetNodeAggregatePortIn
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, \
    offsetInClockCycle


class ArchSyncNodeTerm():
    """
    Class used as a key for ArchElementTermPropagationCtx caches.
    :note: name is excluded from equality operator and hash
    """
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

    :ivar exportedPorts: output ports of ArchElement nodes for every internal out exported
        ArchSyncNodeTerm node is srcNode, out is output defined inside of srcNode
    :ivar importedPorts: output of HlsNetNodeAggregatePortIn for every other arch element port imported into
        ArchSyncNodeTerm node is dstNode and out is out of src ArchElement
    """

    def __init__(self,
                 exportedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut],
                 parentDstElm: ArchElement,
                 stageEnForSyncNode: Dict[ArchSyncNodeTy, HlsNetNodeOut]):
        self.exportedPorts = exportedPorts
        self.importedPorts: Dict[ArchSyncNodeTerm, HlsNetNodeOut] = {}
        self.parentDstElm = parentDstElm
        self.parentDstNode = (parentDstElm, 0)
        self.stageEnForSyncNode = stageEnForSyncNode

    def propagate(self, srcNode: ArchSyncNodeTy, out: HlsNetNodeOut, name: str) -> HlsNetNodeOut:
        assert out
        assert out.obj in srcNode[0].subNodes, (srcNode[0], out, name)
        # export out from srcNode
        kSrc = ArchSyncNodeTerm(srcNode, out, name)
        curE = self.exportedPorts.get(kSrc)
        if curE is None:
            curE = exportPortFromArchElement(srcNode, out, name)
            self.exportedPorts[kSrc] = curE

        # import exported port to dstNode
        dstNode = self.parentDstNode
        kDst = ArchSyncNodeTerm(dstNode, curE, name)
        curI = self.importedPorts.get(kDst)
        if curI is None:
            curI, _ = importPortToArchElement(curE, name, (self.parentDstElm, srcNode[1]))
            self.importedPorts[kDst] = curI
        return curI

    def _propagateFromDstElm_resetTimeForOutInClockWindow(self, elm: ArchElement, clkI: int, dep: HlsNetNodeOut):
        clkBeginTime = clkI * elm.netlist.normalizedClkPeriod
        depTime = dep.obj.scheduledOut[dep.out_i]
        if depTime != clkBeginTime:
            # the dependency time is not at the begin of clk
            # try to search for already existing backedge to clk begin
            for u in dep.obj.usedBy[dep.out_i]:
                if u.in_i == 0 and u.obj.scheduledIn[0] == depTime and isinstance(u.obj, HlsNetNodeWriteBackedge):
                    w: HlsNetNodeWriteBackedge = u.obj
                    r = w.associatedRead
                    if not w._isBlocking and w.allocationType == CHANNEL_ALLOCATION_TYPE.IMMEDIATE and\
                            not r._isBlocking and r.scheduledOut[r._portDataOut.out_i] == clkBeginTime:
                        return r._portDataOut

            # else create a new backedge to clk begin
            r = HlsNetNodeReadBackedge(
                elm.netlist,
                dep._dtype,
                name=f"{dep.getPrettyName():s}_dst",
            )
            r.resolveRealization()
            r._setScheduleZeroTimeSingleClock(clkBeginTime)
            r.setNonBlocking()
            elm._addNodeIntoScheduled(clkI, r)

            w = HlsNetNodeWriteBackedge(
                elm.netlist,
                name=f"{dep.getPrettyName():s}_src")
            w.allocationType = CHANNEL_ALLOCATION_TYPE.IMMEDIATE
            w.resolveRealization()
            w._setScheduleZeroTimeSingleClock(depTime)
            w.setNonBlocking()
            elm._addNodeIntoScheduled(clkI, w)
            w.associateRead(r)

            dep.connectHlsIn(w._inputs[0])

            return r._portDataOut

        return dep

    def _propagateFromDstElm_tryReduceAggregatePort(self, elm: ArchElement, clkI: int, outObj: HlsNetNodeAggregatePortIn, resetTimeToClkWindowBegin:bool) -> Optional[HlsNetNodeOut]:
        # if propagated out source is from dstNode itself, try reuse port already existing there, potentially
        # creating immediate backedge to reset scheduling time of value
        dep = outObj.getDep()
        clkPeriod = dep.obj.netlist.normalizedClkPeriod
        if dep.obj is elm and dep.obj.scheduledOut[dep.out_i] // clkPeriod == clkI:
            depAlreadyInside = HlsNetNodeAggregatePortOut.getDepInside(dep)
            if depAlreadyInside is not None:
                if resetTimeToClkWindowBegin:
                    return self._propagateFromDstElm_resetTimeForOutInClockWindow(
                        elm, clkI, depAlreadyInside)
                return depAlreadyInside
        return None

    def propagateFromDstElm(self, dstNode: ArchSyncNodeTy, out: HlsNetNodeOut, name: str, resetTimeToClkWindowBegin=False) -> HlsNetNodeOut:
        outObj = out.obj
        elm, clkI = dstNode
        assert outObj in self.parentDstElm.subNodes, (self.parentDstElm, out, name)
        # try to reuse existing ports in dstNode
        if isinstance(outObj, HlsNetNodeAggregatePortIn):
            existing = self._propagateFromDstElm_tryReduceAggregatePort(elm, clkI, outObj, resetTimeToClkWindowBegin)
            if existing is not None:
                return existing
        elif isinstance(outObj, HlsNetNodeOperator) and outObj.operator == HwtOps.NOT:
            depOfNot = outObj.dependsOn[0]
            if isinstance(depOfNot.obj, HlsNetNodeAggregatePortIn):
                existing = self._propagateFromDstElm_tryReduceAggregatePort(elm, clkI, depOfNot.obj, resetTimeToClkWindowBegin)
            else:
                existing = None

            if existing is not None:
                if resetTimeToClkWindowBegin:
                    existing = self._propagateFromDstElm_resetTimeForOutInClockWindow(
                        elm, clkI, existing)
                res = elm.builder.buildNot(existing, name=name, opt=False)
                res.obj.resolveRealization()
                scheduleUnscheduledControlLogic(dstNode, res)
                return res

        # export out port from srcNode
        srcNode = (self.parentDstElm, clkI)
        k = ArchSyncNodeTerm(srcNode, out, name)
        curE = self.exportedPorts.get(k)
        exportedPortIsNew = curE is None
        if exportedPortIsNew:
            curE = exportPortFromArchElement(
                srcNode, out, name,
                resetTimeToClkWindowBegin=resetTimeToClkWindowBegin)
            self.exportedPorts[k] = curE

        # import exported port to dstNode
        k = ArchSyncNodeTerm(dstNode, curE, name)
        curI = None if exportedPortIsNew else self.importedPorts.get(k)
        if curI is None:
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
        en, _ = elmNode.getStageEnable(elmNodeClkI)
        en = self.propagate(node, en, f"stateEn_{elmNode._id:d}_{elmNodeClkI:d}")
        self.stageEnForSyncNode[node] = en
        return en


def HlsNetNodeAggregatePortIn_getInput(out_: HlsNetNodeOut):
    """
    :param out_: the output port of HlsNetNodeAggregatePortIn
    """
    userElmIn = out_.obj.parentIn
    userElm: HlsNetNodeAggregate = userElmIn.obj
    dep = userElm.dependsOn[userElmIn.in_i]
    defElm: HlsNetNodeAggregate = dep.obj
    defAggregateOut: HlsNetNodeAggregatePortOut = defElm._outputsInside[dep.out_i]
    return defAggregateOut._inputs[0]


def exportPortFromArchElement(srcNode: ArchSyncNodeTy, out: HlsNetNodeOut, name: str,
                              resetTimeToClkWindowBegin=False):
    elmNode: ArchElement = srcNode[0]
    assert out.obj in elmNode.subNodes, (out.obj, elmNode)
    assert out.obj.scheduledOut is not None, ("Port must be scheduled", out)
    clkPeriod = elmNode.netlist.normalizedClkPeriod
    # to assert that the port is not exported in sooner time
    time = srcNode[1] * clkPeriod
    if not resetTimeToClkWindowBegin:
        time = max(time, out.obj.scheduledOut[out.out_i])
    _out, intern = elmNode._addOutput(out._dtype, name, time=time)
    out.connectHlsIn(intern)
    return _out


def importPortToArchElement(out: HlsNetNodeOut, name: str,
                            dstSyncNode: ArchSyncNodeTy
                            ) -> Tuple[HlsNetNodeOut, SchedTime]:
    srcArchElm: ArchElement = out.obj
    assert isinstance(srcArchElm, ArchElement), ("Only ports of ArchElement instances should be imported", out)
    clkPeriod = srcArchElm.netlist.normalizedClkPeriod
    try:
        assert srcArchElm._outputs[out.out_i] is out, out
    except:
        raise
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
    out.connectHlsIn(outer, checkCycleFree=False)
    return intern, dstTime
