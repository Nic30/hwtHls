from itertools import chain
from typing import Union, List, Type, Dict, Optional, Tuple, Sequence

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If
from hwt.interfaces.std import VldSynced, RdSynced, Signal, Handshaked, \
    HandshakeSync
from hwt.interfaces.structIntf import StructIntf
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite, HlsExplicitSyncNode, \
    HlsReadSync
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.ports import HlsOperationOut
from hwtLib.handshaked.streamNode import StreamNode


def get_sync_type(intf: Interface) -> Type[Interface]:
    """
    resolve wich primiteve type of synchronization is the interface using
    """

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

    def __init__(self, parentHls: "HlsPipeline", name_prefix:str="hls_"):
        self.name_prefix = name_prefix
        self.parentHls = parentHls
        self.node2instance: Dict[
            Union[
                HlsOperationOut,  # any operation output
                Tuple[HlsOperationOut, Interface]  # write
            ],
            TimeIndependentRtlResource] = {}
        # function to create register/signal on RTL level
        self._reg = parentHls.parentUnit._reg
        self._sig = parentHls.parentUnit._sig

    def _instantiate(self, node: Union[AbstractHlsOp,
                                       TimeIndependentRtlResource],
                           used_signals: UniqList[TimeIndependentRtlResourceItem]
                           ) -> TimeIndependentRtlResource:
        """
        Universal RTL instanciation method for all types
        """
        # if isinstance(node, TimeIndependentRtlResource):
        #    # [todo] check if this is really used
        #    used_signals.append(node)
        #    return node
        # else:
        return node.allocate_instance(self, used_signals)

    def _registerSignal(self, origin: HlsOperationOut,
                        s: TimeIndependentRtlResource,
                        used_signals: UniqList[TimeIndependentRtlResourceItem]):
        assert isinstance(s, TimeIndependentRtlResource), s
        assert isinstance(origin, HlsOperationOut), origin
        used_signals.append(s)
        self.node2instance[origin] = s

    def instantiateHlsOperationOut(self, o: HlsOperationOut, used_signals: UniqList[TimeIndependentRtlResourceItem]) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsOperationOut), o
        _o = self.node2instance.get(o, None)

        if _o is None:
            _o = self._instantiate(o.obj, used_signals)
            if _o is not None:
                return _o
            else:
                return self.node2instance[o]
        else:
            used_signals.append(_o)
        return _o

    def allocate(self):
        """
        Allocate scheduled circuit in RTL
        """

        scheduler = self.parentHls.scheduler
        io = self.parentHls._io
        io_aggregation = self.parentHls.io_by_interface
        # is_first_in_pipeline = True
        prev_st_sync_input = None
        prev_st_valid = None
        current_sync = Signal
        for pipeline_st_i, (is_last_in_pipeline, nodes) in enumerate(iter_with_last(scheduler.schedulization)):
            cur_inputs: UniqList[Interface] = UniqList()
            cur_outputs: UniqList[Interface] = UniqList()
            cur_registers: UniqList[TimeIndependentRtlResourceItem] = UniqList()
            assert nodes

            sync_per_io_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem] = {}
            sync_per_io_extraCond: Dict[Interface, TimeIndependentRtlResourceItem] = {}
            for node in nodes:
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                self._instantiate(node, cur_registers)

                if isinstance(node, HlsRead):
                    if len(io_aggregation[node.src]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface", node.src, io_aggregation[node.src])

                    cur_inputs.append(node.src)
                    # if node.src in self.parentHls.coherency_checked_io:
                    self._copy_sync(node.src, node, sync_per_io_skipWhen, sync_per_io_extraCond, cur_registers)

                elif isinstance(node, HlsWrite):
                    if len(io_aggregation[node.dst]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface")

                    cur_outputs.append(io[node.dst])
                    # if node.dst in self.parentHls.coherency_checked_io:
                    self._copy_sync(node.dst, node, sync_per_io_skipWhen, sync_per_io_extraCond, cur_registers)

            prev_st_sync_input, prev_st_valid, current_sync = self.allocate_sync(
                current_sync, cur_inputs, cur_outputs, cur_registers,
                is_last_in_pipeline, pipeline_st_i,
                prev_st_sync_input, prev_st_valid,
                sync_per_io_skipWhen, sync_per_io_extraCond)

    def _copy_sync_single(self, node: Union[HlsRead, HlsWrite], node_inI: int,
                           res: Dict[Interface, TimeIndependentRtlResourceItem],
                           intf: Interface, sync_time: float):
        e = node.dependsOn[node_inI]
        assert intf not in res, intf
        res[intf] = self.node2instance[e].get(sync_time)

    def _copy_sync_all(self, node: Union[HlsRead, HlsWrite, HlsExplicitSyncNode],
                        res_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem],
                        res_extraCond: Dict[Interface, TimeIndependentRtlResourceItem],
                        intf: Interface, sync_time: float):

        if node.skipWhen is not None:
            self._copy_sync_single(node, node.skipWhen_inI, res_skipWhen, intf, sync_time)

        if node.extraCond is not None:
            self._copy_sync_single(node, node.extraCond_inI, res_extraCond, intf, sync_time)

    @staticmethod
    def _numberOfNonSyncUsers(node: HlsRead):
        cnt = 0
        return cnt

    def _copy_sync(self, intf: Interface,
                   node: Union[HlsRead, HlsWrite],
                   res_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem],
                   res_extraCond: Dict[Interface, TimeIndependentRtlResourceItem],
                   used_signals):

        if isinstance(node, HlsRead):
            node: HlsRead
            sync_time = node.scheduledInEnd[0]
            # the node may have only HlsReadSync and HlsExplicitSyncNode users
            # in this case we have to copy the sync from HlsExplicitSyncNode
            onlySuc = None
            for u in node.usedBy[0]:
                u: HlsOperationOut
                if not isinstance(u.obj, HlsReadSync):
                    if onlySuc is None:
                        onlySuc = u.obj
                    else:
                        # we found out some other non HlsReadSync user, we can not copy sync
                        onlySuc = None
                        break

            if isinstance(onlySuc, HlsExplicitSyncNode) and not isinstance(onlySuc, HlsWrite):
                self._instantiate(onlySuc, used_signals)
                self._copy_sync_all(onlySuc, res_skipWhen, res_extraCond, intf, sync_time)

        else:
            assert isinstance(node, (HlsWrite, HlsExplicitSyncNode)), node
            sync_time = node.scheduledIn[0]

        self._copy_sync_all(node, res_skipWhen, res_extraCond, intf, sync_time)

    def _resole_global_sync_type(self, current_sync: Type[Interface], io_channels: Sequence[Interface]):
        for op in io_channels:
            sync_type = get_sync_type(op)
            if sync_type is Handshaked or current_sync is RdSynced and sync_type is VldSynced:
                current_sync = Handshaked
            elif sync_type is RdSynced:
                if current_sync is Handshaked:
                    pass
                elif current_sync is VldSynced:
                    current_sync = Handshaked
                else:
                    current_sync = sync_type
            elif sync_type is VldSynced:
                if current_sync is Handshaked:
                    pass
                elif current_sync is RdSynced:
                    current_sync = Handshaked
                else:
                    current_sync = sync_type
        return current_sync

    def _extract_control_sig_of_interface(
            self,
            intf: Union[HandshakeSync, RdSynced, VldSynced, RtlSignalBase, Signal,
                        Tuple[Union[int, RtlSignalBase, Signal],
                              Union[int, RtlSignalBase, Signal]]]
            ) -> Tuple[Union[int, RtlSignalBase, Signal],
                       Union[int, RtlSignalBase, Signal]]:
        if isinstance(intf, tuple):
            assert len(intf) == 2
            return intf
        elif isinstance(intf, (Handshaked, HandshakeSync)):
            return intf
            # return (intf.vld, intf.rd)
        elif isinstance(intf, VldSynced):
            return (intf.vld, 1)
        elif isinstance(intf, RdSynced):
            return (1, intf.rd)
        elif isinstance(intf, (RtlSignalBase, Signal, StructIntf)):
            return (1, 1)
        else:
            raise TypeError("Unknown synchronisation of ", intf)

    def _collect_rlt_sync(self, sync_per_io: Dict[Interface, TimeIndependentRtlResourceItem], cur_inputs: List[Interface]):
        sync = {}
        # ens_of_stage = []
        for intf, sync_source in sync_per_io.items():
            intf = self._extract_control_sig_of_interface(intf)
            if sync_source:
                if intf == (0, 0):
                    continue
                en = sync_source.data
                if isinstance(en, HandshakeSync):
                    if en not in cur_inputs:
                        cur_inputs.append(en)
                else:
                    sync[intf] = en  # current block en=1

        return sync

    def allocate_sync(self,
                      current_sync: Type[Interface],
                      cur_inputs: UniqList[Interface],
                      cur_outputs: UniqList[Interface],
                      cur_signals: UniqList[TimeIndependentRtlResourceItem],
                      is_last_in_pipeline:bool,
                      pipeline_st_i:int,
                      prev_st_sync_input: Optional[HandshakeSync],
                      prev_st_valid: Optional[RtlSyncSignal],
                      sync_per_io_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem],
                      sync_per_io_extraCond: Dict[Interface, TimeIndependentRtlResourceItem]):
        """
        Allocate synchronization for a single stage of pipeline.
        However the single stage of pipeline may have multiple sections with own validity flag.
        This happens if inputs to this section are driven from the inputs which may be skipped.
        """
        current_sync = self._resole_global_sync_type(current_sync, chain(cur_inputs, cur_outputs))

        if current_sync is not Signal:
            # :note: for a signal we do not need any synchronization
            cur_registers = [
                r.valuesInTime[-1]
                for r in cur_signals
                if r.valuesInTime[-1].is_rlt_register()
            ]

            if is_last_in_pipeline:
                to_next_stage = None
                stage_valid = None
            else:
                # does not need a synchronization with next stage in pipeline
                to_next_stage = Interface_without_registration(
                    self, HandshakeSync(), f"{self.name_prefix:s}stage_sync_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}")
                cur_outputs.append(to_next_stage)
                # if not is_first_in_pipeline:
                # :note: that the register 0 is behind the first stage of pipeline
                stage_valid = self._reg(f"{self.name_prefix:s}stage{pipeline_st_i:d}_valid", def_val=0)
                If(to_next_stage.rd,
                   stage_valid(to_next_stage.vld)
                )

            if cur_inputs or cur_outputs:
                extra_conds = self._collect_rlt_sync(sync_per_io_extraCond, cur_inputs)
                skip_when = self._collect_rlt_sync(sync_per_io_skipWhen, cur_inputs)

                sync = StreamNode(
                    [self._extract_control_sig_of_interface(intf) for intf in cur_inputs],
                    [self._extract_control_sig_of_interface(intf) for intf in cur_outputs],
                    extraConds=extra_conds,
                    skipWhen=skip_when
                )
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

            if prev_st_sync_input is not None:
                # valid is required because otherwise current stage is undefined
                prev_st_sync_input.rd(ack | ~prev_st_valid)

            prev_st_sync_input = to_next_stage
            prev_st_valid = stage_valid

        return prev_st_sync_input, prev_st_valid, current_sync
