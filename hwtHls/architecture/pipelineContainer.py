from itertools import chain
from typing import List, Type, Optional, Dict, Tuple, Union

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Signal, HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.architecturalElement import AllocatorArchitecturalElement
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, resolveStrongestSyncType, \
    SignalsOfStages
from hwtHls.architecture.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode


class AllocatorPipelineContainer(AllocatorArchitecturalElement):
    """
    A container of informations about hw pipeline allocation.
    
    :ivar stages: list of lists of nodes representing the nodes managed by this pipeline in individual clock stages
    :note: stages always start in time 0 and empty lists on beginning marking where the pipeline actually starts.
        This is to have uniform index when we scope into some other element.
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str, stages: List[List[HlsNetNode]]):
        allNodes = UniqList()
        for nodes in stages:
            allNodes.extend(nodes)

        self.stages = stages
        stageCons = [ConnectionsOfStage() for _ in self.stages]
        stageSignals = SignalsOfStages(netlist.normalizedClkPeriod,
                                       (con.signals for con in stageCons))
        AllocatorArchitecturalElement.__init__(self, netlist, namePrefix, allNodes, stageCons, stageSignals)
        self._syncAllocated = False
        self._dataPathAllocated = False

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        if rtl is None or not isinstance(rtl, TimeIndependentRtlResource):
            cons = (self.netNodeToRtl[o] for o in n._outputs if o in self.netNodeToRtl)
        else:
            cons = (rtl,)

        for o in cons:
            o: TimeIndependentRtlResource
            # register all uses
            if o.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
                self.stageSignals.getForTime(o.timeOffset).append(o)

        for dep in n.dependsOn:
            self._afterOutputUsed(dep)

    def allocateDataPath(self, iea: InterArchElementNodeSharingAnalysis):
        assert not self._dataPathAllocated
        assert not self._syncAllocated
        self.interArchAnalysis = iea

        ioToCon: Dict[Interface, ConnectionsOfStage] = {}
        for nodes, con in zip(self.stages, self.connections):
            con: ConnectionsOfStage
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

                if isinstance(node, HlsNetNodeRead):
                    currentStageForIo = ioToCon.get(node.src, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    con.inputs.append(node.src)
                    self._allocateIo(node.src, node, con, ioMuxes, ioSeen, rtl)
                    ioToCon[node.src] = con

                elif isinstance(node, HlsNetNodeWrite):
                    currentStageForIo = ioToCon.get(node.dst, con)
                    assert currentStageForIo is con, ("If the access to IO is from different stage, this should already have IO gate generated", node, con)
                    con.outputs.append(node.dst)
                    # if node.dst in allocator.netlist.coherency_checked_io:
                    self._allocateIo(node.dst, node, con, ioMuxes, ioSeen, rtl)
                    ioToCon[node.dst] = con

            for rtl in self._allocateIoMux(ioMuxes, ioSeen):
                pass

        self._dataPathAllocated = True

    def extendValidityOfRtlResource(self, tir: TimeIndependentRtlResource, endTime: float):
        assert self._dataPathAllocated
        assert not self._syncAllocated
        assert tir.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME
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

    def allocateSync(self):
        assert self._dataPathAllocated
        assert not self._syncAllocated
        prev_st_sync_input = None
        prev_st_valid = None
        
        syncType = Signal
        for con in self.connections:
            syncType = resolveStrongestSyncType(syncType, chain(con.inputs, con.outputs))

        for is_last_in_pipeline, (pipeline_st_i, con) in iter_with_last(enumerate(self.connections)):
            prev_st_sync_input, prev_st_valid = self.allocateSyncForStage(
                con, syncType,
                is_last_in_pipeline, pipeline_st_i,
                prev_st_sync_input, prev_st_valid)
        self._syncAllocated = True

    def allocateSyncForStage(self,
                      con: ConnectionsOfStage,
                      syncType: Type[Interface],
                      is_last_in_pipeline:bool,
                      pipeline_st_i:int,
                      prev_st_sync_input: Optional[HandshakeSync],
                      prev_st_valid: Optional[RtlSyncSignal]):
        """
        Allocate synchronization for a single stage of pipeline.
        However the single stage of pipeline may have multiple sections with own validity flag.
        This happens if inputs to this section are driven from the inputs which may be skipped.

        :note: pipeline registers are placed at the end of the stage
        """

        if syncType is not Signal:
            # :note: Collect registers at the end of this stage
            # because additional synchronization needs to be added
            cur_registers = []
            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(pipeline_st_i + 1)
                if v is not None and v.is_rlt_register():
                    cur_registers.append(v)

            if is_last_in_pipeline:
                to_next_stage = None
                stage_valid = None
            else:
                # does not need a synchronization with next stage in pipeline
                to_next_stage = Interface_without_registration(
                    self, HandshakeSync(), f"{self.namePrefix:s}stage_sync_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}")
                con.outputs.append(to_next_stage)
                # if not is_first_in_pipeline:
                # :note: that the register 0 is behind the first stage of pipeline
                stage_valid = self._reg(f"{self.namePrefix:s}stage{pipeline_st_i:d}_valid", def_val=0)

            if con.inputs or con.outputs:
                sync = con.sync_node = self._makeSyncNode(con)
                en = prev_st_valid

                # check if results of this stage do validity register
                if stage_valid is None:
                    if en is None:
                        sync.sync()
                        ack = sync.ack()
                    else:
                        sync.sync(en)
                        ack = sync.ack() & en

                else:
                    if to_next_stage is None:
                        pass
                    else:
                        _en = en
                        en = (~stage_valid | to_next_stage.rd)
                        if _en is not None:
                            en = en & _en

                    if en is None:
                        sync.sync()
                        ack = sync.ack()
                    else:
                        sync.sync(en)
                        ack = sync.ack() & en

                if cur_registers:
                    # add enable signal for register load derived from synchronization of stage
                    If(ack,
                       *(r.data.next.drivers[0] for r in cur_registers),
                    )

            elif to_next_stage is not None:
                # if is not last
                ack = to_next_stage.rd
                if stage_valid is not None:
                    ack = ack | ~stage_valid

                if prev_st_valid is not None:
                    ack = ack & prev_st_valid
            else:
                ack = BIT.from_py(1)
            
            con.syncNodeAck = ack
            if to_next_stage is not None:
                If(to_next_stage.rd,
                   stage_valid(to_next_stage.vld)
                )

            if prev_st_sync_input is not None:
                # valid is required because otherwise current stage is undefined
                prev_st_sync_input.rd(ack | ~prev_st_valid)

            prev_st_sync_input = to_next_stage
            prev_st_valid = stage_valid

        return prev_st_sync_input, prev_st_valid
