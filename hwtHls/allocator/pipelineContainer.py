from itertools import chain
from typing import List, Type, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If
from hwt.hdl.types.defs import BIT
from hwt.interfaces.std import Signal, HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage, resolveStrongestSyncType, \
    SignalsOfStages
from hwtHls.allocator.interArchElementNodeSharingAnalysis import InterArchElementNodeSharingAnalysis
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode


class AllocatorPipelineContainer(AllocatorArchitecturalElement):
    """
    A container of informations about hw pipeline allocation.
    
    :ivar stages: list of lists of nodes representing the nodes managed by this pipeline in individual clock stages
    :note: stages always start in time 0 and empty lists on beginning marking where the pipeline actually starts.
        This is to have uniform index when we scope into some other element.
    """

    def __init__(self, parentHls: "HlsPipeline", namePrefix:str, stages: List[List[HlsNetNode]]):
        allNodes = UniqList()
        for nodes in stages:
            allNodes.extend(nodes)
            
        self.stages = stages
        stageCons = [ConnectionsOfStage() for _ in self.stages]
        stageSignals = SignalsOfStages(parentHls.normalizedClkPeriod,
                                       (con.signals for con in stageCons))
        AllocatorArchitecturalElement.__init__(self, parentHls, namePrefix, allNodes, stageCons, stageSignals)
        self._syncAllocated = False
        self._dataPathAllocated = False

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        # mark value in register as persisten until the end of fsm
        if rtl is None or not isinstance(rtl, TimeIndependentRtlResource):
            cons = (self.netNodeToRtl[o] for o in n._outputs if o in self.netNodeToRtl)
        else:
            cons = (rtl,)

        for o in cons:
            o: TimeIndependentRtlResource
            # register all uses
            if o.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
                self.stageSignals.getForTime(o.timeOffset).append(o)

        clkPeriod = self.parentHls.normalizedClkPeriod
        for dep in n.dependsOn:
            depRtl = self.netNodeToRtl.get(dep, None)
            if depRtl is not None:
                depRtl: TimeIndependentRtlResource
                if depRtl.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
                    continue
                # in in this arch. element
                # registers uses in new times
                t = o.timeOffset + (len(depRtl.valuesInTime) - 1) * clkPeriod + self.parentHls.schedulerepsilon
                # :note: done in reverse so we do not have to always iterater over registered prequel
                for tir in reversed(depRtl.valuesInTime):
                    sigs = self.stageSignals.getForTime(t)
                    if tir in sigs:
                        break
                    sigs.append(tir)
                    t -= clkPeriod

    def allocateDataPath(self, iea: InterArchElementNodeSharingAnalysis):
        assert not self._dataPathAllocated
        assert not self._syncAllocated
        self.interArchAnalysis = iea
        for nodes, con in zip(self.stages, self.connections):
            # assert nodes
            for node in nodes:
                node: HlsNetNode
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                node.allocateRtlInstance(self)

                if isinstance(node, HlsNetNodeRead):
                    con.inputs.append(node.src)
                    # if node.src in allocator.parentHls.coherency_checked_io:
                    self._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond)

                elif isinstance(node, HlsNetNodeWrite):
                    con.outputs.append(node.dst)
                    # if node.dst in allocator.parentHls.coherency_checked_io:
                    self._copy_sync(node.dst, node, con.io_skipWhen, con.io_extraCond)
        self._dataPathAllocated = True

    def extendValidityOfRtlResource(self, tir: TimeIndependentRtlResource, endTime: float):
        assert self._dataPathAllocated
        assert not self._syncAllocated
        assert tir.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME
        assert endTime > tir.timeOffset, (tir, tir.timeOffset, endTime)

        clkPeriod = self.parentHls.normalizedClkPeriod
        t = tir.timeOffset + (len(tir.valuesInTime) - 1) * clkPeriod + self.parentHls.scheduler.epsilon
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
    
    def rtlResourceInputSooner(self, tir: TimeIndependentRtlResource, newFirstClkIndex: int):
        clkPeriod = self.parentHls.normalizedClkPeriod
        curFirstClkI = int(tir.timeOffset // clkPeriod)
        prequelLen = curFirstClkI - newFirstClkIndex
        assert prequelLen > 0, ("New time must be sooner otherwise there is no point in calling this function")
        tir.timeOffset = newFirstClkIndex * clkPeriod + self.parentHls.scheduler.epsilon
        assert len(tir.valuesInTime) == 1, "Value has to have initial data signal, but can not be used yet"
        valIt = iter(tir.valuesInTime)
        for clkI in range(newFirstClkIndex, curFirstClkI):
            try:
                v = next(valIt)
            except StopIteration:
                break  # the rest will be added later when value is used
            self.stageSignals[clkI].append(v)
    
    def allocateSync(self):
        assert self._dataPathAllocated
        assert not self._syncAllocated
        prev_st_sync_input = None
        prev_st_valid = None
        current_sync = Signal
        for is_last_in_pipeline, (pipeline_st_i, con) in iter_with_last(enumerate(self.connections)):
            prev_st_sync_input, prev_st_valid, current_sync = self.allocateSyncForStage(
                con, current_sync,
                is_last_in_pipeline, pipeline_st_i,
                prev_st_sync_input, prev_st_valid)
        self._syncAllocated = True

    def allocateSyncForStage(self,
                      con: ConnectionsOfStage,
                      current_sync: Type[Interface],
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
        current_sync = resolveStrongestSyncType(current_sync, chain(con.inputs, con.outputs))

        if current_sync is not Signal:
            # :note: Collect registers at the end of this stage
            # because additioal synchronization needs to be added
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

            if to_next_stage is not None:
                If(to_next_stage.rd,
                   stage_valid(to_next_stage.vld)
                )

            if prev_st_sync_input is not None:
                # valid is required because otherwise current stage is undefined
                prev_st_sync_input.rd(ack | ~prev_st_valid)

            prev_st_sync_input = to_next_stage
            prev_st_valid = stage_valid

        return prev_st_sync_input, prev_st_valid, current_sync            
