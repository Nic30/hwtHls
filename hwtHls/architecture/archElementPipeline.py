from itertools import chain
from typing import List, Type, Optional, Dict, Tuple, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If
from hwt.code_utils import rename_signal
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Signal, HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, resolveStrongestSyncType, \
    SignalsOfStages
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, INVARIANT_TIME
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HOrderingVoidT
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from ipCorePackager.constants import INTF_DIRECTION


class ArchElementPipeline(ArchElement):
    """
    A container of informations about hw pipeline allocation.
    
    :ivar stages: list of lists of nodes representing the nodes managed by this pipeline in individual clock stages
    :note: stages always start in time 0 and empty lists on beginning marking where the pipeline actually starts.
        This is to have uniform index when we scope into some other element.
    :ivar _beginClkI: index of the first non-empty stage
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str, stages: List[List[HlsNetNode]]):
        allNodes = UniqList()
        for nodes in stages:
            allNodes.extend(nodes)

        self.stages = stages
        stageCons = [ConnectionsOfStage() for _ in self.stages]
        stageSignals = SignalsOfStages(netlist.normalizedClkPeriod,
                                       (con.signals for con in stageCons))
        ArchElement.__init__(self, netlist, namePrefix, allNodes, stageCons, stageSignals)
        self._syncAllocated = False
        self._dataPathAllocated = False
        self._beginClkI: Optional[int] = None

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        isTir = isinstance(rtl, TimeIndependentRtlResource)
        
        if isinstance(n, HlsNetNodeWriteBackwardEdge) and n.allocationType == BACKEDGE_ALLOCATION_TYPE.REG:
            clkPeriod = self.netlist.normalizedClkPeriod
            con: ConnectionsOfStage = self.connections[n.scheduledIn[0] // clkPeriod]
            con.stDependentDrives.append(rtl)
        # elif isinstance(n, HlsProgramStarter):
        #    assert isTir, n
        #    # because we want to consume token from the starter only on transition in this FSM
        #    con: ConnectionsOfStage = self.connections[0]
        #    con.stDependentDrives.append(rtl.valuesInTime[0].data.next.drivers[0])

        if rtl is None or not isTir:
            cons = (self.netNodeToRtl[o] for o in n._outputs if o in self.netNodeToRtl if o._dtype is not HOrderingVoidT)

        else:
            cons = (rtl,)

        for o in cons:
            o: TimeIndependentRtlResource
            # register all uses
            if o.timeOffset is not INVARIANT_TIME:
                self.stageSignals.getForTime(o.timeOffset).append(o)

        for dep in n.dependsOn:
            self._afterOutputUsed(dep)
            
    def _privatizeLocalOnlyBackedges(self):
        clkPeriod = self.netlist.normalizedClkPeriod
        
        for stI, nodes in enumerate(self.stages):
            for node in nodes:
                if isinstance(node, HlsNetNodeReadBackwardEdge):
                    w = node.associated_write
                    if w.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER and w in self.allNodes and w.scheduledIn[0] // clkPeriod == stI:
                        w.allocationType = BACKEDGE_ALLOCATION_TYPE.REG  # allocate as a register because this is connect just this stage with itself
       
    def allocateDataPath(self, iea: InterArchElementNodeSharingAnalysis):
        assert not self._dataPathAllocated
        assert not self._syncAllocated
        
        self.interArchAnalysis = iea
        self._privatizeLocalOnlyBackedges()

        ioDiscovery: HlsNetlistAnalysisPassDiscoverIo = self.netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverIo)
        ioToCon: Dict[Interface, ConnectionsOfStage] = {}
        allIoObjSeen = set()
        beginFound = False
        self._beginClkI = 0

        for stI, (nodes, con) in enumerate(zip(self.stages, self.connections)):
            con: ConnectionsOfStage
            if not beginFound:
                if not nodes and not con.inputs and not con.outputs:
                    # if there is nothing in this stage, we skip it
                    continue
                else:
                    beginFound = True
                    self._beginClkI = stI

            # assert nodes
            ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]] = {}
            ioSeen: UniqList[Interface] = UniqList()
            for node in nodes:
                node: HlsNetNode
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                wasInstantiated = node._outputs and node._outputs[0] not in self.netNodeToRtl
                rtl = node.allocateRtlInstance(self)
                if wasInstantiated:
                    self._afterNodeInstantiated(node, rtl)

                if node in allIoObjSeen:
                    # io mux constructed in previous stage
                    continue

                if isinstance(node, HlsNetNodeRead):
                    if isinstance(node, HlsNetNodeReadBackwardEdge):
                        if node.associated_write.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
                            # only buffer has an explicit IO from pipeline
                            continue

                    currentStageForIo = ioToCon.get(node.src, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    con.inputs.append(node.src)
                    self._allocateIo(ioDiscovery, node.src, node, con, ioMuxes, ioSeen, rtl)
                    ioToCon[node.src] = con
                    allIoObjSeen.add(node)

                elif isinstance(node, HlsNetNodeWrite):
                    if isinstance(node, HlsNetNodeWriteBackwardEdge):
                        if node.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
                            # only buffer has an explicit IO from pipeline
                            continue

                    currentStageForIo = ioToCon.get(node.dst, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    con.outputs.append(node.dst)
                    # if node.dst in allocator.netlist.coherency_checked_io:
                    self._allocateIo(ioDiscovery, node.dst, node, con, ioMuxes, ioSeen, rtl)
                    ioToCon[node.dst] = con
                    allIoObjSeen.add(node)

            for rtl in self._allocateIoMux(ioMuxes, ioSeen):
                pass

        self._dataPathAllocated = True

    def extendValidityOfRtlResource(self, tir: TimeIndependentRtlResource, endTime: float):
        assert self._dataPathAllocated
        assert not self._syncAllocated
        assert tir.timeOffset is not INVARIANT_TIME
        assert endTime > tir.timeOffset, (tir, tir.timeOffset, endTime)

        clkPeriod = self.netlist.normalizedClkPeriod
        t = tir.timeOffset + (len(tir.valuesInTime) - 1) * clkPeriod + self.netlist.scheduler.epsilon
        assert t < endTime
        # :note: done in reverse so we do not have to always iterater over registered prequel
        while t <= endTime:
            t += clkPeriod
            i = int(t // clkPeriod)
            if i >= len(self.stageSignals):
                self.stageSignals.append(UniqList())
                self.stages.append([])
                self.connections.append(ConnectionsOfStage())

            sigs = self.stageSignals.getForTime(t)
            assert tir not in sigs
            tir.get(t)
            sigs.append(tir)

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        if clkI < self._beginClkI:
            self._beginClkI = clkI
        super(ArchElementPipeline, self).connectSync(clkI, intf, intfDir)

    def allocateSync(self):
        assert self._dataPathAllocated
        assert not self._syncAllocated
        
        syncType = Signal
        for con in self.connections:
            syncType = resolveStrongestSyncType(syncType, chain(con.inputs, con.outputs))

        prev_st_valid = None
        for is_last_in_pipeline, (pipeline_st_i, con) in iter_with_last(enumerate(self.connections)):
            con: ConnectionsOfStage
            if pipeline_st_i < self._beginClkI:
                continue
            self.allocateSyncForStage(
                prev_st_valid,
                con, syncType,
                None if is_last_in_pipeline else self.connections[pipeline_st_i + 1],
                pipeline_st_i)
            prev_st_valid = con.stageDataVld
        self._syncAllocated = True

    def allocateSyncForStage(self,
                      prevStageDataVld: Optional[RtlSyncSignal],
                      con: ConnectionsOfStage,
                      syncType: Type[Interface],
                      nextCon: Optional[ConnectionsOfStage],
                      pipeline_st_i:int):
        """
        Allocate synchronization for a single stage of pipeline.
        Each pipeline represents only a straight pipeline. Each non-last stage is equipped with a stage_N_valid register.
        The 1 in this stage represents that the stage registers are occupied and can accept data only if data can be flushed to successor stage.
        There is stage_sync_N_to_N+1 synchronization channel which synhronizes the data movement between stages.
        The channel is ready if next stage is able to process new data. And valid if data are provided from this stage.
        
        :note: pipeline registers are placed visually at the end of the non-last stage
        """

        if syncType is not Signal:
            # :note: Collect registers at the end of this stage
            # because additional synchronization needs to be added
            curRegisterDrivers = []
            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(pipeline_st_i)
                if v.isExplicitRegister:
                    curRegisterDrivers.append(v.data.next.drivers[0])
                else:
                    v = s.checkIfExistsInClockCycle(pipeline_st_i + 1)
                    if v is not None and v.is_rlt_register():
                        curRegisterDrivers.append(v.data.next.drivers[0])
            curRegisterDrivers.extend(con.stDependentDrives)
            
            if nextCon is None:
                toNextStSource = None
                toNextStSink = None
                stValid = None
            else:
                # need a synchronization if there is a next stage in the pipeline
                toNextStSource = Interface_without_registration(
                    self, HandshakeSync(), f"{self.namePrefix:s}stSync_st{pipeline_st_i:d}_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}")
                con.outputs.append(toNextStSource)
                con.syncOut = toNextStSource

                toNextStSink = Interface_without_registration(
                    self, HandshakeSync(), f"{self.namePrefix:s}stSync_st{pipeline_st_i+1:d}_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}")
                nextCon.inputs.append(toNextStSink)
                nextCon.syncIn = toNextStSink
                # if not is_first_in_pipeline:
                # :note: that the register 0 is behind the first stage of pipeline
                con.stageDataVld = stValid = self._reg(f"{self.namePrefix:s}st{pipeline_st_i:d}_valid", def_val=0)

            if con.inputs or con.outputs:
                sync = con.sync_node = self._makeSyncNode(prevStageDataVld, con)
                # check if results of this stage do validity register
                sync.sync()
                ack = sync.ack()
                ack = rename_signal(self.netlist.parentUnit, ack, f"{self.namePrefix}st{pipeline_st_i:d}_ack")
                if curRegisterDrivers:
                    # add enable signal for register load derived from synchronization of stage
                    If(ack,
                       *curRegisterDrivers,
                    )

            else:
                # 1 stage no input/output
                ack = BIT.from_py(1)
            
            con.syncNodeAck = ack
            if toNextStSource is not None:
                If(toNextStSink.rd | ~stValid,
                    stValid(ack)
                )
                toNextStSource.rd(toNextStSink.rd | ~stValid)
                toNextStSink.vld(stValid)  # valid only if data is in registers

