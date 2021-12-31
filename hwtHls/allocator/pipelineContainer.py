from itertools import chain
from typing import List, Dict, Union, Type, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If
from hwt.interfaces.std import Signal, HandshakeSync
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage, resolveStrongestSyncType
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite
from hwtHls.netlist.nodes.ops import AbstractHlsOp


class PipelineContainer(AllocatorArchitecturalElement):

    def __init__(self, allocator: "HlsAllocator", stages: List[List[AbstractHlsOp]],
                 io_by_interface: Dict[Interface, List[Union["HlsRead", "HlsWrite"]]]):
        AllocatorArchitecturalElement.__init__(self, allocator)
        self.stages = stages
        self.io_by_interface = io_by_interface

    def allocateDataPath(self):
        io_aggregation = self.io_by_interface
        connections_of_stage = self.connections
        allocator = self.allocator

        # is_first_in_pipeline = True
        for nodes in self.stages:
            con = ConnectionsOfStage()
            # assert nodes
            for node in nodes:
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                allocator._instantiate(node, con.signals)

                if isinstance(node, HlsRead):
                    if len(io_aggregation[node.src]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface", node.src, io_aggregation[node.src])

                    con.inputs.append(node.src)
                    # if node.src in allocator.parentHls.coherency_checked_io:
                    allocator._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond, con.signals)

                elif isinstance(node, HlsWrite):
                    if len(io_aggregation[node.dst]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface")

                    con.outputs.append(node.dst)
                    # if node.dst in allocator.parentHls.coherency_checked_io:
                    allocator._copy_sync(node.dst, node, con.io_skipWhen, con.io_extraCond, con.signals)

            connections_of_stage.append(con)

    def allocateSync(self):
        prev_st_sync_input = None
        prev_st_valid = None
        current_sync = Signal
        for is_last_in_pipeline, (pipeline_st_i, con) in iter_with_last(enumerate(self.connections)):
            prev_st_sync_input, prev_st_valid, current_sync = self.allocateSyncForStage(
                con, current_sync,
                is_last_in_pipeline, pipeline_st_i,
                prev_st_sync_input, prev_st_valid)

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
        allocator = self.allocator

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
                    allocator, HandshakeSync(), f"{allocator.name_prefix:s}stage_sync_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}")
                con.outputs.append(to_next_stage)
                # if not is_first_in_pipeline:
                # :note: that the register 0 is behind the first stage of pipeline
                stage_valid = allocator._reg(f"{allocator.name_prefix:s}stage{pipeline_st_i:d}_valid", def_val=0)

            if con.inputs or con.outputs:
                sync = con.sync_node = allocator._makeSyncNode(con)
                # print(f"############# stage {pipeline_st_i:d} #############")
                # print("extra_conds")
                # for i, c in sorted([(i._name, c) for i, c in extra_conds.items()], key=lambda x: x[0]):
                #    print(f"\t{i}: \t{c}")
                #
                # print("skip_when")
                # for i, c in sorted([(i._name, c) for i, c in skip_when.items()], key=lambda x: x[0]):
                #    print(f"\t{i}: \t{c}")

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

            else:
                ack = to_next_stage.rd
                if stage_valid is not None:
                    ack = ack | ~stage_valid

                if prev_st_valid is not None:
                    ack = ack & prev_st_valid

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
