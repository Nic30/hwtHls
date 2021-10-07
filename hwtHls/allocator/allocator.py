from itertools import chain
from typing import Union, List, Type, Dict, Optional

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.struct import HStruct
from hwt.interfaces.hsStructIntf import HsStructIntf
from hwt.interfaces.std import VldSynced, RdSynced, Signal, Handshaked, \
    HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.codeOps import HlsRead, HlsOperation, HlsWrite, AbstractHlsOp
from hwtHls.hlsPipeline import HlsPipeline
from hwtLib.handshaked.streamNode import StreamNode


def get_sync_type(intf: Interface) -> Type[Interface]:
    if isinstance(intf, HandshakeSync):
        return Handshaked
    elif isinstance(intf, VldSynced):
        return VldSynced
    elif isinstance(intf, RdSynced):
        return RdSynced
    else:
        assert isinstance(intf, (Signal, RtlSignal)), intf
        return Signal


class HlsAllocator():
    """
    Convert virtual operation instances to real RTL code

    :ivar parentHls: parent HLS context for this allocator
    :ivar node2instance: dictionary {hls node: rtl instance}
    """

    def __init__(self, parentHls: HlsPipeline):
        self.parentHls = parentHls
        self.node2instance: Dict[Union[HlsOperation,
                                       HlsRead,
                                       HlsWrite], TimeIndependentRtlResource] = {}
        # function to create register on RTL level
        self._reg = parentHls.parentUnit._reg
        self._sig = parentHls.parentUnit._sig

    def _instantiate(self, node: Union[HlsOperation,
                                       HlsRead,
                                       HlsWrite],
                           used_signals: UniqList[TimeIndependentRtlResourceItem]
                           ) -> TimeIndependentRtlResource:
        """
        Universal RTL instanciation method for all types
        """
        if isinstance(node, TimeIndependentRtlResource):
            used_signals.append(node)
            return node
        elif isinstance(node, HlsRead):
            return self.instantiateRead(node, used_signals)
        elif isinstance(node, HlsWrite):
            return self.instantiateWrite(node, used_signals)
        else:
            return node.allocate_instance(self, used_signals)

    def _registerSignal(self, origin: AbstractHlsOp,
                        s: TimeIndependentRtlResource,
                        used_signals: UniqList[TimeIndependentRtlResourceItem]):
        assert isinstance(s, TimeIndependentRtlResource), s
        used_signals.append(s)
        self.node2instance[origin] = s

    def instantiateRead(self, readOp: HlsRead,
                         used_signals: UniqList[TimeIndependentRtlResourceItem]) -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        _o = TimeIndependentRtlResource(
            readOp.getRtlDataSig(),
            readOp.scheduledInEnd[0],
            self)
        self._registerSignal(readOp, _o, used_signals)

        return _o

    def instantiateWrite(self, write: HlsWrite,
                         used_signals: UniqList[TimeIndependentRtlResourceItem]
                         ) -> List[HdlAssignmentContainer]:
        """
        Instantiate write operation on RTL level
        """
        assert len(write.dependsOn) == 1, write.dependsOn
        dep = write.dependsOn[0]
        o = dep.obj
        # if isinstance(o, HlsMux) and o in self.node2instance:
        #    return []

        try:
            _o = self.node2instance[o]
        except KeyError:
            # o should be instance of TimeIndependentRtlResource itself
            _o = None

        if _o is None:
            _o = self._instantiate(o, used_signals)
        else:
            used_signals.append(_o)

        # apply indexes before assignments
        dst = write.dst
        try:
            # translate HlsIo object to signal
            dst = self.parentHls._io[dst]
        except KeyError:
            pass
        _dst = dst
        if isinstance(dst, HsStructIntf):
            dst = dst.data

        if write.indexes is not None:
            for i in write.indexes:
                dst = dst[i]
        try:
            # skip instantiation of writes in the same mux
            return self.node2instance[(o, dst)]
        except KeyError:
            pass

        assert o is not _o, (o, _o)
        assert isinstance(_o, TimeIndependentRtlResource), _o

        _o = _o.get(o.scheduledInEnd[0])

        rtlObj = dst(_o.data)
        self.node2instance[o] = rtlObj
        self.node2instance[(o, dst)] = rtlObj

        return rtlObj

    def allocate_sync(self,
                      current_sync: Type[Interface],
                      cur_inputs: UniqList[Interface],
                      cur_outputs: UniqList[Interface],
                      cur_registers: UniqList[TimeIndependentRtlResourceItem],
                      is_last_in_pipeline:bool,
                      pipeline_st_i:int,
                      prev_st_sync_input: Optional[HandshakeSync],
                      prev_st_valid: Optional[RtlSyncSignal]):
        """
        Allocate synchronization for a single stage of pipeline
        """
        for op in chain(cur_inputs, cur_outputs):
            sync_type = get_sync_type(op)
            if sync_type is Handshaked or current_sync is RdSynced and sync_type is VldSynced:
                current_sync = Handshaked
            elif sync_type is RdSynced and sync_type is VldSynced:
                current_sync = sync_type

        if current_sync is not Signal:
            # :note: for a signal we do not need any synchronization
            cur_registers = [r.valuesInTime[-1] for r in cur_registers if r.valuesInTime[-1].is_rlt_register()]
            if not is_last_in_pipeline:
                # does not need a synchronization with next stage in pipeline
                to_next_stage = self._sig(f"stage_sync_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}",
                                          HStruct(
                                              (BIT, "rd"),
                                              (BIT, "vld"))
                                        )
                cur_outputs.append(to_next_stage)
                # if not is_first_in_pipeline:
                # :note: that the register 0 is behind the first stage of pipeline
                stage_valid = self._reg(f"stage{pipeline_st_i:d}_valid", def_val=0)
            else:
                to_next_stage = None
                stage_valid = None

            if prev_st_sync_input is not None:
                # :note: we want to allow flushing if no io is involved
                cur_inputs.append((prev_st_valid, prev_st_sync_input.rd))
                If(prev_st_sync_input.rd,
                   prev_st_valid(prev_st_sync_input.vld)
                ).Else(
                   prev_st_valid(prev_st_valid | prev_st_sync_input.vld)
                )

            if cur_inputs or cur_outputs:
                sync = StreamNode(cur_inputs, cur_outputs)
                sync.sync()
                if cur_registers:
                    # add enable signal for register load derived from synchronization of stage
                    If(sync.ack() | ~prev_st_valid,
                       *(r.data.next.drivers[0] for r in cur_registers)
                    )

            prev_st_sync_input = to_next_stage
            prev_st_valid = stage_valid

        return prev_st_sync_input, prev_st_valid, current_sync

    def allocate(self):
        """
        Allocate scheduled circuit in RTL
        """
        scheduler = self.parentHls.scheduler
        io = self.parentHls._io
        # is_first_in_pipeline = True
        prev_st_sync_input = None
        prev_st_valid = None
        current_sync = Signal
        for pipeline_st_i, (is_last_in_pipeline, nodes) in enumerate(iter_with_last(scheduler.schedulization)):
            cur_inputs: UniqList[Interface] = UniqList()
            cur_outputs: UniqList[Interface] = UniqList()
            cur_registers: UniqList[TimeIndependentRtlResourceItem] = UniqList()
            for node in nodes:
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                self._instantiate(node, cur_registers)

                if isinstance(node, HlsRead):
                    cur_inputs.append(node.intf)
                elif isinstance(node, HlsWrite):
                    cur_outputs.append(io[node.dst])

            prev_st_sync_input, prev_st_valid, current_sync = self.allocate_sync(
                current_sync, cur_inputs, cur_outputs, cur_registers,
                is_last_in_pipeline, pipeline_st_i,
                prev_st_sync_input, prev_st_valid)

