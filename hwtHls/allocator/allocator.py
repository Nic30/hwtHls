from typing import Union, List, Dict, Tuple

from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage, \
    extract_control_sig_of_interface, SignalsOfStages
from hwtHls.allocator.fsmContainer import AllocatorFsmContainer
from hwtHls.allocator.pipelineContainer import AllocatorPipelineContainer
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.analysis.fsm import HlsNetlistAnalysisPassDiscoverFsm, IoFsm
from hwtHls.netlist.analysis.pipeline import HlsNetlistAnalysisPassDiscoverPipelines, \
    NetlistPipeline
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync, \
    HlsNetNodeReadSync
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtLib.handshaked.streamNode import StreamNode
from hwt.hdl.statements.statement import HdlStatement


class HlsAllocator():
    """
    Convert virtual operation instances to real RTL code

    :ivar parentHls: parent HLS context for this allocator
    :ivar netNodeToRtl: dictionary {hls node: rtl instance}
    """

    def __init__(self, parentHls: "HlsPipeline", name_prefix:str="hls_"):
        self.name_prefix = name_prefix
        self.parentHls = parentHls
        self.netNodeToRtl: Dict[
            Union[
                HlsNetNodeOut,  # any operation output
                Tuple[HlsNetNodeOut, Interface]  # write
            ],
            TimeIndependentRtlResource] = {}
        # function to create register/signal on RTL level
        self._reg = parentHls.parentUnit._reg
        self._sig = parentHls.parentUnit._sig
        self._archElements: List[Union[AllocatorFsmContainer, AllocatorPipelineContainer]] = []

    def _registerSignal(self, origin: HlsNetNodeOut,
                        s: TimeIndependentRtlResource,
                        used_signals: UniqList[TimeIndependentRtlResourceItem]):
        assert isinstance(s, TimeIndependentRtlResource), s
        assert isinstance(origin, HlsNetNodeOut), origin
        used_signals.append(s)
        self.netNodeToRtl[origin] = s

    def instantiateHlsNetNodeOut(self,
                                   o: HlsNetNodeOut,
                                   used_signals: SignalsOfStages
                                   ) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            # new allocation, use registered automatically
            _o = o.obj.allocateRtlInstance(self, used_signals)
            if _o is None:
                return self.netNodeToRtl[o]
        else:
            # used and previously allocated
            # used_signals.getForTime(t).append(_o)
            pass

        return _o

    def instantiateHlsNetNodeOutInTime(self,
                                   o: HlsNetNodeOut,
                                   time:float,
                                   used_signals: SignalsOfStages
                                   ) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        _o = self.instantiateHlsNetNodeOut(o, used_signals)
        if isinstance(_o, TimeIndependentRtlResource):
            return _o.get(time)
        else:
            return _o

    def allocate(self):
        """
        Allocate scheduled circuit in RTL
        """
        hls = self.parentHls
        fsms: HlsNetlistAnalysisPassDiscoverFsm = hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverFsm)
        pipelines: HlsNetlistAnalysisPassDiscoverPipelines = hls.requestAnalysis(HlsNetlistAnalysisPassDiscoverPipelines)
        
        for fsm in fsms.fsms:
            fsm: IoFsm
            fsmCont = AllocatorFsmContainer(self, fsm)
            self._archElements.append(fsmCont)

        for pipe in pipelines.pipelines:
            pipe: NetlistPipeline
            pipeCont = AllocatorPipelineContainer(self, pipe.stages)
            self._archElements.append(pipeCont)

        if len(self._archElements) > 1:
            for e in self._archElements:
                # [todo] first boundary signals needs to be declared, then the body of fsm/pipeline can be constructed
                #    because there is no topological order in how the elements are connected
                e.declareIo()

        for e in self._archElements:
            e.allocateDataPath()
            e.allocateSync()

    def _copy_sync_single(self, node: Union[HlsNetNodeRead, HlsNetNodeWrite], node_inI: int,
                           res: Dict[Interface, TimeIndependentRtlResourceItem],
                           intf: Interface, sync_time: float):
        e = node.dependsOn[node_inI]
        assert intf not in res, (intf, "already has sync in this stage")
        res[intf] = self.netNodeToRtl[e].get(sync_time)

    def _copy_sync_all(self, node: Union[HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync],
                        res_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem],
                        res_extraCond: Dict[Interface, TimeIndependentRtlResourceItem],
                        intf: Interface, sync_time: float):

        if node.skipWhen is not None:
            self._copy_sync_single(node, node.skipWhen_inI, res_skipWhen, intf, sync_time)

        if node.extraCond is not None:
            self._copy_sync_single(node, node.extraCond_inI, res_extraCond, intf, sync_time)

    def _copy_sync(self, intf: Interface,
                   node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                   res_skipWhen: Dict[Interface, TimeIndependentRtlResourceItem],
                   res_extraCond: Dict[Interface, TimeIndependentRtlResourceItem],
                   used_signals):

        if isinstance(node, HlsNetNodeRead):
            node: HlsNetNodeRead
            sync_time = node.scheduledOut[0]
            # the node may have only HlsNetNodeReadSync and HlsNetNodeExplicitSync users
            # in this case we have to copy the sync from HlsNetNodeExplicitSync
            onlySuc = None
            for u in node.usedBy[0]:
                u: HlsNetNodeOut
                if not isinstance(u.obj, HlsNetNodeReadSync):
                    if onlySuc is None:
                        onlySuc = u.obj
                    else:
                        # we found out some other non HlsNetNodeReadSync user, we can not copy sync
                        onlySuc = None
                        break

            if isinstance(onlySuc, HlsNetNodeExplicitSync) and not isinstance(onlySuc, HlsNetNodeWrite):
                onlySuc.allocateRtlInstance(self, used_signals)
                self._copy_sync_all(onlySuc, res_skipWhen, res_extraCond, intf, sync_time)

        else:
            assert isinstance(node, (HlsNetNodeWrite, HlsNetNodeExplicitSync)), node
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
