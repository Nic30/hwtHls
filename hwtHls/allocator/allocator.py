from typing import Union, List, Dict, Tuple, Deque

from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage, \
    extract_control_sig_of_interface, SignalsOfStages
from hwtHls.allocator.fsmContainer import FsmContainer
from hwtHls.allocator.pipelineContainer import PipelineContainer
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.pipeline import HlsNetlistAnalysisPassDiscoverPipelines, \
    NetlistPipeline
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite, HlsExplicitSyncNode, \
    HlsReadSync
from hwtHls.netlist.nodes.ports import HlsOperationOut
from hwtLib.handshaked.streamNode import StreamNode


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
        self._archElements: List[Union[FsmContainer, PipelineContainer]] = []

    def _registerSignal(self, origin: HlsOperationOut,
                        s: TimeIndependentRtlResource,
                        used_signals: UniqList[TimeIndependentRtlResourceItem]):
        assert isinstance(s, TimeIndependentRtlResource), s
        assert isinstance(origin, HlsOperationOut), origin
        used_signals.append(s)
        self.node2instance[origin] = s

    def instantiateHlsOperationOut(self,
                                   o: HlsOperationOut,
                                   used_signals: SignalsOfStages
                                   ) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsOperationOut), o
        _o = self.node2instance.get(o, None)

        if _o is None:
            # new allocation, use registered automatically
            _o = o.obj.allocate_instance(self, used_signals)
            if _o is None:
                return self.node2instance[o]
            else:
                return _o
        else:
            # used and previously allocated
            used_signals.append(_o)

        return _o

    def instantiateHlsOperationOutInTime(self,
                                   o: HlsOperationOut,
                                   time:float,
                                   used_signals: SignalsOfStages
                                   ) -> TimeIndependentRtlResourceItem:
        _o = self.instantiateHlsOperationOut(o, used_signals)
        return _o.get(time)

    def allocate(self):
        """
        Allocate scheduled circuit in RTL
        """
        hls = self.parentHls
        fsms: HlsNetlistAnalysisPassDiscoverFsm = hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        pipelines: HlsNetlistAnalysisPassDiscoverPipelines = hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverPipelines)
        
        for fsm in fsms.fsms:
            fsm: IoFsm
            fsmCont = FsmContainer(self, fsm)
            fsmCont.allocateDataPath()
            fsmCont.allocateSync()
            self._archElements.append(fsmCont)

        for pipe in pipelines.pipelines:
            pipe: NetlistPipeline
            pipeCont = PipelineContainer(self, pipe.stages)
            pipeCont.allocateDataPath()
            pipeCont.allocateSync()
            self._archElements.append(pipeCont)

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
                onlySuc.allocate_instance(self, used_signals)
                self._copy_sync_all(onlySuc, res_skipWhen, res_extraCond, intf, sync_time)

        else:
            assert isinstance(node, (HlsWrite, HlsExplicitSyncNode)), node
            sync_time = node.scheduledIn[0]

        self._copy_sync_all(node, res_skipWhen, res_extraCond, intf, sync_time)

    def _collect_rlt_sync(self, sync_per_io: Dict[Interface, TimeIndependentRtlResourceItem], cur_inputs: List[Interface]):
        sync = {}
        # ens_of_stage = []
        for intf, sync_source in sync_per_io.items():
            intf = extract_control_sig_of_interface(intf)
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
    
    def _makeSyncNode(self, con: ConnectionsOfStage):
        extra_conds = self._collect_rlt_sync(con.io_extraCond, con.inputs)
        skip_when = self._collect_rlt_sync(con.io_skipWhen, con.inputs)

        masters = [extract_control_sig_of_interface(intf) for intf in con.inputs]
        slaves = [extract_control_sig_of_interface(intf) for intf in con.outputs]
        sync = StreamNode(
            masters,
            slaves,
            extraConds=extra_conds if masters or slaves else None,
            skipWhen=skip_when if masters or slaves else None,
        )
        con.sync_node = sync
        return sync
