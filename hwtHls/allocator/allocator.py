from itertools import chain
from typing import Union, List, Type, Dict, Optional, Tuple, Sequence, Set

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import If, SwitchLogic, Switch
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.interfaces.std import VldSynced, RdSynced, Signal, Handshaked, \
    HandshakeSync
from hwt.interfaces.structIntf import StructIntf
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.unitImplHelpers import Interface_without_registration
from hwt.synthesizer.rtlLevel.constants import NOT_SPECIFIED
from hwt.synthesizer.rtlLevel.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite, HlsExplicitSyncNode, \
    HlsReadSync
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.netlist.nodes.ports import HlsOperationOut
from hwtLib.amba.axi_intf_common import Axi_hs
from hwtLib.handshaked.streamNode import StreamNode


def get_sync_type(intf: Interface) -> Type[Interface]:
    """
    resolve wich primitive type of synchronization is the interface using
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


class ConnectionsOfStage():
    """
    Container of connections of pipeline stage or FSM state
    """

    def __init__(self):
        self.inputs: UniqList[Interface] = UniqList()
        self.outputs: UniqList[Interface] = UniqList()
        self.signals: UniqList[TimeIndependentRtlResourceItem] = UniqList()
        self.io_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem] = {}
        self.io_extraCond: Dict[Interface, TimeIndependentRtlResourceItem] = {}
        self.sync_node: Optional[StreamNode] = None
        self.stDependentDrives: List[HdlStatement] = []


def setNopValIfNotSet(intf: Interface, nopVal, exclude: List[Interface]):
    if intf in exclude:
        return
    elif intf._interfaces:
        for _intf in intf._interfaces:
            setNopValIfNotSet(_intf, nopVal, exclude)
    elif intf._sig._nop_val is NOT_SPECIFIED:
        intf._sig._nop_val = intf._dtype.from_py(nopVal) 


def getIntfSyncSignals(intf: Interface) -> Tuple[Interface, ...]:
    if isinstance(intf, (HandshakeSync, Handshaked)):
        return (intf.rd, intf.vld)
    elif isinstance(intf, Axi_hs):
        return (intf.ready, intf.valid)
    elif isinstance(intf, (RtlSignal, Signal)):
        return ()
    elif isinstance(intf, VldSynced):
        return (intf.vld,)
    elif isinstance(intf, RdSynced):
        return (intf.rd,)
    else:
        raise NotImplementedError(intf)


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
        self._connections_of_stage: List[ConnectionsOfStage] = []

    def _instantiate(self, node: Union[AbstractHlsOp,
                                       TimeIndependentRtlResource],
                           used_signals: UniqList[TimeIndependentRtlResourceItem]
                           ) -> TimeIndependentRtlResource:
        """
        Universal RTL instanciation method for all types
        """
        return node.allocate_instance(self, used_signals)

    def _registerSignal(self, origin: HlsOperationOut,
                        s: TimeIndependentRtlResource,
                        used_signals: UniqList[TimeIndependentRtlResourceItem]):
        assert isinstance(s, TimeIndependentRtlResource), s
        assert isinstance(origin, HlsOperationOut), origin
        used_signals.append(s)
        self.node2instance[origin] = s

    def instantiateHlsOperationOut(self,
                                   o: HlsOperationOut,
                                   used_signals: UniqList[TimeIndependentRtlResourceItem]
                                   ) -> TimeIndependentRtlResource:
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
        io_aggregation = self.parentHls.requestAnalysis(HlsNetlistAnalysisPassDiscoverIo).io_by_interface
        fsms: HlsNetlistAnalysisPassDiscoverFsm = self.parentHls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        fsmNodes = fsms.collectInFsmNodes()
        scheduler.schedulization = [
            [n for n in sch if n not in fsmNodes]
            for sch in scheduler.schedulization
        ]
        for fsm in fsms.fsms:
            self.allocateFsm(fsm)

        connections_of_stage = self._connections_of_stage = []
        # is_first_in_pipeline = True
        for pipeline_st_i, (is_last_in_pipeline, nodes) in enumerate(iter_with_last(scheduler.schedulization)):
            con = ConnectionsOfStage()
            # assert nodes
            for node in nodes:
                # this is one level of nodes,
                # node can not be dependent on nodes behind in this list
                # because this engine does not support backward edges in DFG
                self._instantiate(node, con.signals)

                if isinstance(node, HlsRead):
                    if len(io_aggregation[node.src]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface", node.src, io_aggregation[node.src])

                    con.inputs.append(node.src)
                    # if node.src in self.parentHls.coherency_checked_io:
                    self._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond, con.signals)

                elif isinstance(node, HlsWrite):
                    if len(io_aggregation[node.dst]) > 1:
                        raise AssertionError("In this phase each IO operation should already have separate gate"
                                             " if it wants to access same interface")

                    con.outputs.append(node.dst)
                    # if node.dst in self.parentHls.coherency_checked_io:
                    self._copy_sync(node.dst, node, con.io_skipWhen, con.io_extraCond, con.signals)

            connections_of_stage.append(con)

        prev_st_sync_input = None
        prev_st_valid = None
        current_sync = Signal
        for is_last_in_pipeline, (pipeline_st_i, (nodes, con)) in iter_with_last(enumerate(zip(scheduler.schedulization,
                                                                                               connections_of_stage))):
            prev_st_sync_input, prev_st_valid, current_sync = self.allocate_sync(
                con, current_sync,
                is_last_in_pipeline, pipeline_st_i,
                prev_st_sync_input, prev_st_valid)

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

    def _copy_sync(self, intf: Interface,
                   node: Union[HlsRead, HlsWrite],
                   res_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem],
                   res_extraCond: Dict[Interface, TimeIndependentRtlResourceItem],
                   used_signals):

        if isinstance(node, HlsRead):
            node: HlsRead
            sync_time = node.scheduledOut[0]
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

    def _resolve_global_sync_type(self, current_sync: Type[Interface], io_channels: Sequence[Interface]):
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
    
    # def _moveNodeToClk(self, node: AbstractHlsOp, clk_i: int):
    #    """
    #    Move the node in time to specified clk
    #    """
    #    clk_period = self.parentHls.clk_period
    #    off = (clk_i - min(node.scheduledIn) // clk_period) * clk_period
    #    node.scheduledIn = tuple(t + off for t in node.scheduledIn)
    #    node.scheduledOut = tuple(t + off for t in node.scheduledOut)

    def allocateFsm(self, fsm: IoFsm):
        """
        :note: This function does not perform efficient register allocations.
            Instead each value is store in idividual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
            
        """
        assert fsm.states, fsm
        clk_period = self.parentHls.clk_period
        st = self._reg(f"fsm_st_{fsm.intf._name}", Bits(log2ceil(len(fsm.states)), signed=False), def_val=0)
        
        # initialize nop value which will drive the IO when not used
        for stI, nodes in enumerate(fsm.states):
            for node in nodes:
            #    self._moveNodeToClk(node, fsmBeginClk_i)
                if isinstance(node, HlsWrite):
                    intf = node.dst
                    # to prevent latching when interface is not used
                    syncSignals = getIntfSyncSignals(intf)
                    setNopValIfNotSet(intf, None, syncSignals)
                elif isinstance(node, HlsRead):
                    intf = node.src
                    syncSignals = getIntfSyncSignals(intf)
                else:
                    syncSignals = None
                
                if syncSignals is not None:
                    for s in syncSignals:
                        setNopValIfNotSet(s, 0, ())
        
        # instantiate logic in the states
        fsmBeginClk_i = int(min(min(node.scheduledIn) for node in fsm.states[0]) // clk_period)
        fsmEndClk_i = int(max(max(*node.scheduledIn, *node.scheduledOut, 0) for node in fsm.states[-1]) // clk_period)
        stateCons: List[ConnectionsOfStage] = []
        for stI, nodes in enumerate(fsm.states):
            con = ConnectionsOfStage()
            stateCons.append(con)
            for node in nodes:
                rtl = self._instantiate(node, con.signals)

                if isinstance(node, HlsRead):
                    if not isinstance(node.src, (Signal, RtlSignal)):
                        con.inputs.append(node.src)
                    self._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond, con.signals)

                elif isinstance(node, HlsWrite):
                    con.stDependentDrives.append(rtl)
                    if not isinstance(node.src, (Signal, RtlSignal)):
                        con.outputs.append(node.dst)
                    self._copy_sync(node.dst, node, con.io_skipWhen, con.io_extraCond, con.signals)

            # mark value in register as persisten until the end of fsm
            for s in con.signals:
                s: TimeIndependentRtlResource
                if not s.persistenceRanges:
                    # val for the first clock behind this is int the register and the rest is persistent
                    nextClkI = start_clk(s.timeOffset, clk_period) + 2
                    if nextClkI <= fsmEndClk_i:
                        s.persistenceRanges.append((nextClkI, fsmEndClk_i))
        
        # instantiate control of the FSM
        seenRegs: Set[TimeIndependentRtlResource] = set()
        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        for stI, (nodes, con) in enumerate(zip(fsm.states, stateCons)):
            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(fsmBeginClk_i + stI + 1)
                if v is not None and v.is_rlt_register() and not v in seenRegs:
                    con.stDependentDrives.append(v.data.next.drivers[0])
                    seenRegs.add(v)

            unconditionalTransSeen = False
            inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            sync = self._makeSyncNode(con)
            for dstSt, c in sorted(fsm.transitionTable[stI].items(), key=lambda x: x[0]):
                assert not unconditionalTransSeen
                c = sync.ack() & c
                if c == 1:
                    unconditionalTransSeen = True
                    inStateTrans.append((c, st(dstSt)))
                else:
                    inStateTrans.append((c, st(dstSt)))
            stateTrans.append((stI, [SwitchLogic(inStateTrans),
                                     con.stDependentDrives,
                                     sync.sync()]))

        return Switch(st).add_cases(stateTrans)
    
    def _makeSyncNode(self, con: ConnectionsOfStage):
        extra_conds = self._collect_rlt_sync(con.io_extraCond, con.inputs)
        skip_when = self._collect_rlt_sync(con.io_skipWhen, con.inputs)

        masters = [self._extract_control_sig_of_interface(intf) for intf in con.inputs
             if not isinstance(RtlSignal, Signal)]
        slaves = [self._extract_control_sig_of_interface(intf) for intf in con.outputs
             if not isinstance(RtlSignal, Signal)]
        sync = StreamNode(
            masters,
            slaves,
            extraConds=extra_conds if masters or slaves else None,
            skipWhen=skip_when if masters or slaves else None,
        )
        con.sync_node = sync
        return sync

    def allocate_sync(self,
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
        current_sync = self._resolve_global_sync_type(current_sync, chain(con.inputs, con.outputs))

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
                    self, HandshakeSync(), f"{self.name_prefix:s}stage_sync_{pipeline_st_i:d}_to_{pipeline_st_i+1:d}")
                con.outputs.append(to_next_stage)
                # if not is_first_in_pipeline:
                # :note: that the register 0 is behind the first stage of pipeline
                stage_valid = self._reg(f"{self.name_prefix:s}stage{pipeline_st_i:d}_valid", def_val=0)

            if con.inputs or con.outputs:
                sync = con.sync_node = self._makeSyncNode(con)
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
