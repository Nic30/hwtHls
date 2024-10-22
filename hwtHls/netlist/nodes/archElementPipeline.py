from itertools import islice
from typing import List, Dict, Tuple, Union, Generator, Optional

from hwt.code import If
from hwt.hdl.const import HConst
from hwt.hwIO import HwIO
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    ConnectionsOfStageList
from hwtHls.architecture.timeIndependentRtlResource import INVARIANT_TIME, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class ArchElementPipeline(ArchElement):
    """
    This HlsNetNode represents a hardware pipeline. Pipeline is composed of linearly connected groups of nodes.

    .. figure:: ./_static/ArchElementPipeline.png

    :see: `~.ArchElement`

    :ivar stages: list of lists of nodes representing the nodes managed by this pipeline in individual clock stages
    :note: stages always start in time 0 and empty lists on beginning marking where the pipeline actually starts.
        This is to have uniform index when we scope into some other element.
    """

    def __init__(self, netlist: HlsNetlistCtx,
                 name: str, namePrefix:str,
                 subNodes: SetList[HlsNetNode]=None,
                 stages: List[List[HlsNetNode]]=None):
        if subNodes is None:
            hadStagesButNoSubNodes = bool(stages)
            subNodes = SetList()
        else:
            hadStagesButNoSubNodes = False

        if stages is None:
            self.stages = []
            stageCons = ConnectionsOfStageList(netlist.normalizedClkPeriod, ())
        else:
            self.stages = stages
            stageCons = ConnectionsOfStageList(netlist.normalizedClkPeriod,
                                               (ConnectionsOfStage(self, clkI)
                                                for clkI, _ in enumerate(self.stages)))
        ArchElement.__init__(self, netlist, name, namePrefix, subNodes, stageCons)

        if hadStagesButNoSubNodes:
            # add nodes from stages to subNodes and initialize parent
            for nodes in stages:
                self.addNodes(nodes)

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = ArchElement.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.stages = [[n.clone(memo, True)[0] for n in nodes] for nodes in self.stages]
        return y, isNew

    def getBeginEndClkI(self) -> Tuple[int, int]:
        beginClkI = None
        endClkI = None
        for stI, (nodes, con) in enumerate(zip(self.stages, self.connections)):
            con: ConnectionsOfStage
            if not nodes and (con is None or (not con.inputs and not con.outputs)):
                # if there is nothing in this stage, we skip it
                continue
            else:
                if beginClkI is None:
                    beginClkI = stI
                endClkI = stI

        assert beginClkI is not None, self
        assert endClkI is not None, self
        return (beginClkI, endClkI)

    @override
    def addImplicitSyncChannelsInsideOfElm(self):
        """
        Construct HlsNetNodeWriteForwardedge/HlsNetNodeReadForwardedge pairs connecting pipeline stages.
        """
        netlist = self.netlist
        clkPeriod: SchedTime = netlist.normalizedClkPeriod
        epsilon: SchedTime = netlist.scheduler.epsilon
        ffdelay = netlist.platform.get_ff_store_time(netlist.realTimeClkPeriod, netlist.scheduler.resolution)

        previousClkI = None
        connections = self.connections
        changed = False
        for clkI, _ in self.iterStages():
            if previousClkI is not None:
                # build r/w node pairs for sync between pipeline stages (previousClkI -> clkI)
                wTime = ((previousClkI + 1) * clkPeriod) - ffdelay - epsilon  # end of previous clock
                dummyC = HlsNetNodeConst(netlist, HVoidOrdering.from_py(None))
                dummyC.resolveRealization()
                dummyC._setScheduleZeroTimeSingleClock(wTime - epsilon)
                # allowNewClockWindow=True because the empty stage may be there to implement delay
                self._addNodeIntoScheduled(clkI, dummyC, allowNewClockWindow=True)

                name = f"{self.namePrefix:s}stSync_{previousClkI:d}_to_{clkI:d}"
                wNode = HlsNetNodeWriteForwardedge(netlist,
                                                   mayBecomeFlushable=False,
                                                   name=f"{name}_atSrc")
                wNode.resolveRealization()
                wNode._setScheduleZeroTimeSingleClock(wTime)  # at the end of previousClkI
                self._addNodeIntoScheduled(previousClkI, wNode)
                dummyC._outputs[0].connectHlsIn(wNode._portSrc)

                rNode = HlsNetNodeReadForwardedge(netlist, dtype=HVoidOrdering,
                                                  name=f"{name:s}_atDst")
                assert clkI >= 1, clkI
                rNode.resolveRealization()
                rNode._setScheduleZeroTimeSingleClock((clkI * clkPeriod) + epsilon)  # at the beginning of ClkI
                wNode.associateRead(rNode)
                self._addNodeIntoScheduled(clkI, rNode)
                con: ConnectionsOfStage = connections[clkI]
                con.pipelineSyncIn = rNode
                changed = True

            previousClkI = clkI
        return changed

    @override
    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        beginClkI = self._beginClkI
        endClkI = self._endClkI
        for clkI, nodes in enumerate(self.stages):
            if beginClkI is not None and clkI < beginClkI:
                assert not nodes, (self, clkI, nodes)
                continue
            if endClkI is not None and clkI > endClkI:
                return
            if beginClkI is None and nodes:
                beginClkI = clkI
            if beginClkI is not None:
                yield (clkI, nodes)

    def isBeginStage(self, clkIndex: int) -> bool:
        assert len(self.stages) > clkIndex
        return all(st is None for st in islice(self.stages, 0, clkIndex)) and self.stages[clkIndex] is not None

    def isLastStage(self, clkIndex: int) -> bool:
        assert len(self.stages) > clkIndex
        return len(self.stages) - 1 == clkIndex or (
            all(st is None for st in islice(self.stages, clkIndex + 1))
        )

    @override
    def getStageForClock(self, clkIndex: int, createIfNotExists=False) -> List[HlsNetNode]:
        assert clkIndex >= 0, clkIndex
        stages = self.stages
        if createIfNotExists and len(stages) <= clkIndex:
            stages.extend([] for _ in range(len(stages), clkIndex + 1))

        return stages[clkIndex]

    @override
    def getStageEnable(self, clkIndex: int) -> Tuple[Optional[HlsNetNodeOut], bool]:
        if not any(nodes and clkI < clkIndex for (clkI, nodes) in self.iterStages()):
            return None, False  # first stage of pipeline
        return super().getStageEnable()

    def removeStage(self, clkIndex: int):
        assert not self.stages[clkIndex], ("can not remove non empty stage", self, clkIndex)
        self.connections[clkIndex] = None
        if self._beginClkI == clkIndex:
            self._beginClkI += 1
            while self.getStageForClock(self._beginClkI) is None:
                self._beginClkI += 1

    @override
    def rtlRegisterOutputRtlSignal(self, outOrTime: Union[HlsNetNodeOut, SchedTime], data: Union[RtlSignal, HwIO, HConst],
                 isExplicitRegister: bool, isForwardDeclr: bool,
                 mayChangeOutOfCfg: bool):
        tir = super(ArchElementPipeline, self).rtlRegisterOutputRtlSignal(
            outOrTime, data, isExplicitRegister, isForwardDeclr, mayChangeOutOfCfg)

        # if isinstance(outOrTime, HlsNetNodeOut):
        #    n = outOrTime.obj
        #    if isinstance(n, HlsNetNodeReadBackedge) and n.associatedWrite.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
        #        clkPeriod = self.netlist.normalizedClkPeriod
        #        con: ConnectionsOfStage = self.connections[n.scheduledIn[0] // clkPeriod]
        #        con.stateChangeDependentDrives.append(tir)

        if tir.timeOffset is not INVARIANT_TIME:
            self.connections.getForTime(tir.timeOffset).signals.append(tir.valuesInTime[0])
        return tir

    def _privatizeLocalOnlyChannels(self):
        clkPeriod = self.netlist.normalizedClkPeriod

        for stI, nodes in self.iterStages():
            for node in nodes:
                if isinstance(node, HlsNetNodeReadBackedge):
                    w = node.associatedWrite
                    if w.allocationType == CHANNEL_ALLOCATION_TYPE.BUFFER and w in self.subNodes and w.scheduledIn[0] // clkPeriod == stI:
                        # allocate as a register because this is connect just this stage with itself
                        w.allocationType = CHANNEL_ALLOCATION_TYPE.REG

    @override
    def rtlStatesMayHappenConcurrently(self, stateClkI0: int, stateClkI1: int):
        return stateClkI0 != stateClkI1

    @override
    def rtlAllocDatapath(self):
        assert not self._rtlDatapathAllocated
        assert not self._rtlSyncAllocated

        self._privatizeLocalOnlyChannels()

        # dictionaries to assert that the IO is accessed only in a single stage
        rToCon: Dict[HwIO, ConnectionsOfStage] = {}
        wToCon: Dict[HwIO, ConnectionsOfStage] = {}
        for (nodes, con) in zip(self.stages, self.connections):
            if not nodes:
                assert con is None, self
                continue

            con: ConnectionsOfStage
            assert con is not None, self
            for node in nodes:
                node: HlsNetNode
                assert not node._isMarkedRemoved, node
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                if node._isRtlAllocated:
                    continue

                assert node.parent is self, ("Check if node parent is set correctly", node, node.parent, self)
                assert node.scheduledIn is not None, ("Node must be scheduled", node)
                assert node.dependsOn is not None, ("Node must not be destroyed", node)
                node.rtlAlloc(self)

                if isinstance(node, HlsNetNodeRead):
                    if isinstance(node, HlsNetNodeReadBackedge):
                        if node.associatedWrite.allocationType != CHANNEL_ALLOCATION_TYPE.BUFFER:
                            # only buffer has an explicit IO from pipeline
                            continue

                    if node.src is None:
                        # local only channel
                        assert isinstance(node, HlsProgramStarter) or\
                            (isinstance(node, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)) and
                                node.associatedWrite in self.subNodes
                            ) or (
                                not node._rtlUseReady and
                                not node._rtlUseValid and
                                HdlType_isVoid(node._portDataOut._dtype)
                            ), node
                        continue

                    currentStageForIo = rToCon.get(node.src, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    rToCon[node.src] = con

                elif isinstance(node, HlsNetNodeWrite):
                    if isinstance(node, HlsNetNodeWriteBackedge):
                        if node.allocationType != CHANNEL_ALLOCATION_TYPE.BUFFER:
                            # only buffer has an explicit IO from pipeline
                            continue

                    if node.dst is None:
                        # local only channel
                        assert (isinstance(node, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)) and
                                node.associatedRead in self.subNodes
                                ) or (
                                      not node._rtlUseReady and
                                      not node._rtlUseValid and
                                      HdlType_isVoid(node.dependsOn[0]._dtype)
                                     ), node
                        continue

                    currentStageForIo = wToCon.get(node.dst, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    wToCon[node.dst] = con

        for con in self.connections:
            if con is None:
                continue
            for _ in con.rtlAllocIoMux():
                pass
        self._rtlDatapathAllocated = True

    @override
    def rtlAllocSync(self):
        assert self._rtlDatapathAllocated, self
        assert not self._rtlSyncAllocated, self
        self._beginClkI, self._endClkI = self.getBeginEndClkI()
        if self._beginClkI is None:
            # completely empty element
            assert self._endClkI is None, self
            for (pipeline_st_i, con) in enumerate(self.connections):
                con: ConnectionsOfStage
                assert con.isUnused(), (self, pipeline_st_i, self._beginClkI, con)
        else:
            for (pipeline_st_i, con) in enumerate(self.connections):
                con: ConnectionsOfStage
                if pipeline_st_i < self._beginClkI:
                    assert con is None or con.isUnused(), (self, pipeline_st_i, self._beginClkI, con)
                else:
                    self.rtlAllocSyncForStage(con, pipeline_st_i)

        self._rtlSyncAllocated = True

    def rtlAllocSyncForStage(self, con: ConnectionsOfStage, pipeline_st_i:int):
        """
        Allocate synchronization for a single stage of pipeline.
        Each pipeline represents only a straight pipeline. Each non-last stage is equipped with a stage_N_valid register.
        The 1 in this stage represents that the stage registers are occupied and can accept data only
        if data can be flushed to successor stage.
        There is stage_sync_N_to_N+1 synchronization channel which synchronizes the data movement between stages.
        The channel is ready if next stage is able to process new data. And valid if data are provided from this stage.

        :note: pipeline registers are placed visually at the end of the non-last stage
        """
        # :note: Collect registers at the end of this stage
        # because additional synchronization needs to be added
        nextStRegDrivers = SetList()
        for curV in con.signals:
            curV: TimeIndependentRtlResourceItem
            s = curV.parent
            # if the value has a register at the end of this stage
            nextStVal = s.checkIfExistsInClockCycle(pipeline_st_i + 1)
            if nextStVal is not None and nextStVal.isRltRegister():
                nextStRegDrivers.append(nextStVal.data.next.drivers[0])

        nextStRegDrivers.extend(con.stateChangeDependentDrives)

        #if con.inputs or con.outputs:
        #    con.rtlChannelSyncFinalize(self.netlist.parentHwModule,
        #                               self._dbgAddSignalNamesToSync,
        #                               self._dbgExplicitlyNamedSyncSignals)
        #con.rtlAllocSync()
        # check if results of this stage do validity register
        ack = con.stageAck
        if isinstance(ack, (HConst, int)):
            ack = int(ack)
            assert ack == 1, ("If stage ack is a constant, it must be 1, otherwise this stage is always stalling", self, pipeline_st_i, con, ack)
        else:

            if con.stageEnable is not None:
                if con.pipelineSyncIn is None:
                    con.stageEnable(1)  # there are no implicit data
                else:
                    con.stageEnable(con.pipelineSyncIn.src.vld)

            if nextStRegDrivers:
                assert ack is not None, ("stageAck should be already pre-filled by HlsNetNodeFsmStateAck", self, pipeline_st_i, nextStRegDrivers)
                # add enable signal for register load derived from synchronization of stage
                If(ack,
                   *nextStRegDrivers,
                )

