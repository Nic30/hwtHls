from typing import Union, Literal, List, Optional, Tuple, Generator, Self

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStageList
from hwtHls.architecture.timeIndependentRtlResource import INVARIANT_TIME
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortIn, \
    HlsNetNodeAggregatePortOut
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeStageAck
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.scheduler.clk_math import offsetInClockCycle


class ArchElementNoImplicitSync(ArchElement):
    """
    This is a specific type of ArchElement without any additional sync added during conversion to RTL.

    :attention: All inputs are at the time 0 + offset in their clock cycle and can be directly connected to any other cycle.

    This node is intended to be used only for connections which do not follow typical program order.
    A typical example of usage is broadcast in a pipeline. 
    """

    def __init__(self, netlist:"HlsNetlistCtx", name:str, namePrefix:str,
            subNodes:SetList[HlsNetNode],
            connections:ConnectionsOfStageList):
        ArchElement.__init__(self, netlist, name, namePrefix, subNodes, connections)
        self.stages = [[] for _ in connections]
        self._beginClkI = 0
        self._endClkI = len(connections)

    @classmethod
    def createEmptyScheduledInstance(cls, netlist:"HlsNetlistCtx", name:str, namePrefix:Optional[str]=None) -> Self:
        if namePrefix is None:
            namePrefix = name + "_"
        elm = cls(netlist, name, namePrefix,
                  SetList(),
                  ConnectionsOfStageList(netlist.normalizedClkPeriod))
        elm.resolveRealization()
        elm._setScheduleZeroTimeSingleClock(0)
        netlist.addNode(elm)
        return elm

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = ArchElement.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.stages = [[n.clone(memo, True)[0] for n in nodes] for nodes in self.stages]
        return y, isNew

    @override
    def _addInput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeIn, HlsNetNodeOut]:
        """
        :attention: see attention in class doc.
        """
        i, internI = super(ArchElementNoImplicitSync, self)._addInput(t, name, time=time)
        if time is not None:
            clkPeriod = self.netlist.normalizedClkPeriod
            clkI = time // clkPeriod
            _internIObj = self.stages[clkI].pop()
            assert _internIObj is internI.obj, (_internIObj, internI.obj)
            self.stages[0].append(_internIObj)

            _internIObj._setScheduleZero(offsetInClockCycle(time, clkPeriod))

        return i, internI

    @override
    def rtlRegisterOutputRtlSignal(self,
                               outOrTime: Union[HlsNetNodeOut, SchedTime],
                               data: Union[RtlSignal, HwIO, HConst],
                               isExplicitRegister: bool,
                               isForwardDeclr: bool,
                               mayChangeOutOfCfg: bool,
                               timeOffset: Union[SchedTime, Literal[INVARIANT_TIME, NOT_SPECIFIED]]=NOT_SPECIFIED):
        assert timeOffset is NOT_SPECIFIED, (
            "Node in ArchElementNoImplicitSync may only use RTL signals which do not have any timeOffset specification", data, timeOffset)
        timeOffset = INVARIANT_TIME  # in this arch element the time does not matter because there is no sync
        return super(ArchElementNoImplicitSync, self).rtlRegisterOutputRtlSignal(
            outOrTime, data, isExplicitRegister, isForwardDeclr, mayChangeOutOfCfg, timeOffset=timeOffset)

    def getStageForClock(self, clkIndex: int, createIfNotExists=False) -> List[HlsNetNode]:
        return ArchElementPipeline.getStageForClock(self, clkIndex, createIfNotExists=createIfNotExists)

    @override
    def getStageEnable(self, clkIndex: int) -> Tuple[Optional[HlsNetNodeOut], bool]:
        raise AssertionError("There is no stage enable because body of this element is not divided to stages")

    def getStageAckNode(self, clkIndex: int) -> Tuple[HlsNetNodeStageAck, bool]:
        raise AssertionError("There is no stage ack because body of this element is not divided to stages")

    @override
    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        return ArchElementPipeline.iterStages(self)

    @override
    def rtlStatesMayHappenConcurrently(self, stateClkI0: int, stateClkI1: int):
        return True

    @override
    def rtlAllocSync(self):
        pass
        #for con in self.connections:
        #    if con is None:
        #        continue
        #    con.rtlChannelSyncFinalize(self.netlist.parentHwModule,
        #                       self._dbgAddSignalNamesToSync, self._dbgExplicitlyNamedSyncSignals)
        #    con.rtlAllocSync()
        #
    @override
    def rtlAllocDatapath(self):
        assert not self._rtlDatapathAllocated
        assert not self._rtlSyncAllocated

        for node in self.subNodes:
            node: Union[HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut]
            if node._isRtlAllocated:
                continue

            assert node.scheduledIn is not None, ("Node must be scheduled", node)
            assert node.dependsOn is not None, ("Node must not be destroyed", node)
            node.rtlAlloc(self)

        for con in self.connections:
            if con is None:
                continue
            for _ in con.rtlAllocIoMux():
                pass

        self._rtlDatapathAllocated = True
