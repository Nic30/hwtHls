from typing import List, Dict, Tuple, Union, Generator

from hwt.code import If
from hwt.code_utils import rename_signal
from hwt.hdl.value import HValue
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    ConnectionsOfStageList
from hwtHls.architecture.timeIndependentRtlResource import INVARIANT_TIME, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.analysis.betweenSyncIslands import BetweenSyncIsland
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HVoidOrdering, HdlType_isVoid
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, link_hls_nodes
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.typingFuture import override


class ArchElementPipeline(ArchElement):
    """
    This HlsNetNode represents a hardware pipeline. Pipeline is composed of linearly connected groups of nodes.

    .. figure:: ./_static/ArchElementPipeline.png

    :see: `~.ArchElement`

    :ivar syncIsland: synchronization regions which are handled by this element
    :ivar stages: list of lists of nodes representing the nodes managed by this pipeline in individual clock stages
    :note: stages always start in time 0 and empty lists on beginning marking where the pipeline actually starts.
        This is to have uniform index when we scope into some other element.
    """

    def __init__(self, netlist: HlsNetlistCtx, name: str, subNodes: UniqList[HlsNetNode],
                 stages: List[List[HlsNetNode]], syncIsland: BetweenSyncIsland):
        self.syncIsland = syncIsland
        self.stages = stages
        stageCons = ConnectionsOfStageList(netlist.normalizedClkPeriod, (ConnectionsOfStage(self, clkI) for clkI, _ in enumerate(self.stages)))
        ArchElement.__init__(self, netlist, name, subNodes, stageCons)

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
            if not nodes and not con.inputs and not con.outputs:
                # if there is nothing in this stage, we skip it
                continue
            else:
                if beginClkI is None:
                    beginClkI = stI
                endClkI = stI
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
        for clkI, _ in self.iterStages():
            if previousClkI is not None:
                # build r/w node pairs for sync between pipeline stages (previousClkI -> clkI)
                wTime = ((previousClkI + 1) * clkPeriod) - ffdelay - epsilon  # end of previous clock
                dummyC = HlsNetNodeConst(netlist, HVoidOrdering.from_py(None))
                dummyC.resolveRealization()
                dummyC._setScheduleZeroTimeSingleClock(wTime - epsilon)
                self._addNodeIntoScheduled(clkI, dummyC)

                name = f"{self.name:s}stSync_{previousClkI:d}_to_{clkI:d}"
                wNode = HlsNetNodeWriteForwardedge(netlist,
                                                   name=f"{name}_atSrc")
                link_hls_nodes(dummyC._outputs[0], wNode._inputs[0])
                wNode.resolveRealization()
                wNode._setScheduleZeroTimeSingleClock(wTime)  # at the end of previousClkI
                self._addNodeIntoScheduled(previousClkI, wNode)

                rNode = HlsNetNodeReadForwardedge(netlist, dtype=HVoidOrdering,
                                                  name=f"{name:s}_atDst")
                assert clkI >= 1, clkI
                rNode.resolveRealization()
                rNode._setScheduleZeroTimeSingleClock((clkI * clkPeriod) + epsilon)  # at the beginning of ClkI
                wNode.associateRead(rNode)
                self._addNodeIntoScheduled(clkI, rNode)
                con: ConnectionsOfStage = connections[clkI]
                con.implicitSyncFromPrevStage = rNode

            previousClkI = clkI

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

    @override
    def getStageForClock(self, clkIndex: int) -> List[HlsNetNode]:
        return self.stages[clkIndex]

    @override
    def rtlRegisterOutputRtlSignal(self, outOrTime: Union[HlsNetNodeOut, SchedTime], data: Union[RtlSignal, Interface, HValue],
                 isExplicitRegister: bool, isForwardDeclr: bool,
                 mayChangeOutOfCfg: bool):
        tir = super(ArchElementPipeline, self).rtlRegisterOutputRtlSignal(
            outOrTime, data, isExplicitRegister, isForwardDeclr, mayChangeOutOfCfg)

        # if isinstance(outOrTime, HlsNetNodeOut):
        #    n = outOrTime.obj
        #    if isinstance(n, HlsNetNodeReadBackedge) and n.associatedWrite.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
        #        clkPeriod = self.netlist.normalizedClkPeriod
        #        con: ConnectionsOfStage = self.connections[n.scheduledIn[0] // clkPeriod]
        #        con.stDependentDrives.append(tir)

        if tir.timeOffset is not INVARIANT_TIME:
            self.connections.getForTime(tir.timeOffset).signals.append(tir.valuesInTime[0])
        return tir

    def _privatizeLocalOnlyChannels(self):
        clkPeriod = self.netlist.normalizedClkPeriod

        for stI, nodes in enumerate(self.stages):
            for node in nodes:
                if isinstance(node, HlsNetNodeReadBackedge):
                    w = node.associatedWrite
                    if w.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER and w in self._subNodes and w.scheduledIn[0] // clkPeriod == stI:
                        # allocate as a register because this is connect just this stage with itself
                        w.allocationType = BACKEDGE_ALLOCATION_TYPE.REG

    @override
    def rtlStatesMayHappenConcurrently(self, stateClkI0: int, stateClkI1: int):
        return stateClkI0 != stateClkI1

    @override
    def rtlAllocDatapath(self):
        assert not self._rtlDatapathAllocated
        assert not self._rtlSyncAllocated

        self._privatizeLocalOnlyChannels()

        # dictionaries to assert that the IO is accessed only in a single stage
        rToCon: Dict[Interface, ConnectionsOfStage] = {}
        wToCon: Dict[Interface, ConnectionsOfStage] = {}
        for (nodes, con) in zip(self.stages, self.connections):
            con: ConnectionsOfStage
            for node in nodes:
                node: HlsNetNode
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                if node._isRtlAllocated:
                    continue

                assert node.scheduledIn is not None, ("Node must be scheduled", node)
                assert node.dependsOn is not None, ("Node must not be destroyed", node)
                node.rtlAlloc(self)

                if isinstance(node, HlsNetNodeRead):
                    if isinstance(node, HlsNetNodeReadBackedge):
                        if node.associatedWrite.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
                            # only buffer has an explicit IO from pipeline
                            continue

                    if node.src is None:
                        # local only channel
                        assert (
                            isinstance(node, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)) and
                            node.associatedWrite in self._subNodes
                            ) or (
                                not node._rtlUseReady and
                                not node._rtlUseValid and
                                HdlType_isVoid(node._outputs[0]._dtype)
                                ), node
                        continue

                    currentStageForIo = rToCon.get(node.src, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    rToCon[node.src] = con

                elif isinstance(node, HlsNetNodeWrite):
                    if isinstance(node, HlsNetNodeWriteBackedge):
                        if node.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
                            # only buffer has an explicit IO from pipeline
                            continue

                    if node.dst is None:
                        # local only channel
                        assert (isinstance(node, (HlsNetNodeWriteBackedge, HlsNetNodeWriteForwardedge)) and
                                node.associatedRead in self._subNodes
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
            for _ in self._rtlAllocIoMux(con.ioMuxes, con.ioMuxesKeysOrdered):
                pass
        self._rtlDatapathAllocated = True

    @override
    def rtlAllocSync(self):
        assert self._rtlDatapathAllocated, self
        assert not self._rtlSyncAllocated, self
        self._beginClkI, self._endClkI = self.getBeginEndClkI()

        for (pipeline_st_i, con) in enumerate(self.connections):
            con: ConnectionsOfStage
            if pipeline_st_i < self._beginClkI:
                assert con.isUnused(), (self, pipeline_st_i, self._beginClkI, con)
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
        nextStRegDrivers = UniqList()
        for curV in con.signals:
            curV: TimeIndependentRtlResourceItem
            s = curV.parent
            # if the value has a register at the end of this stage
            nextStVal = s.checkIfExistsInClockCycle(pipeline_st_i + 1)
            if nextStVal is not None and nextStVal.isRltRegister():
                nextStRegDrivers.append(nextStVal.data.next.drivers[0])

        nextStRegDrivers.extend(con.stDependentDrives)

        if con.inputs or con.outputs:
            sync = con.syncNode = self._rtlAllocateSyncStreamNode(con)
            # check if results of this stage do validity register
            sync.sync()
            ack = sync.ack()
            if isinstance(ack, (HValue, int)):
                ack = int(ack)
                assert ack == 1, ("If statge ack is a constant, it must be 1, otherwise this stage is always stalling", self, pipeline_st_i, con, ack)
                if con.syncNodeAck is not None:
                    assert not con.syncNodeAck.drivers
                    con.syncNodeAck(1)
            else:
                if con.syncNodeAck is None:
                    ack = rename_signal(self.netlist.parentUnit, ack, f"{self.name:s}st{pipeline_st_i:d}_ack")
                    con.syncNodeAck = ack
                else:
                    assert not con.syncNodeAck.drivers
                    con.syncNodeAck(ack)
                    ack = con.syncNodeAck

                if con.stageEnable is not None:
                    if con.implicitSyncFromPrevStage is None:
                        con.stageEnable(1)  # there are no implicit data
                    else:
                        con.stageEnable(con.implicitSyncFromPrevStage.src.vld)

                if nextStRegDrivers:
                    # add enable signal for register load derived from synchronization of stage
                    If(ack,
                       *nextStRegDrivers,
                    )

