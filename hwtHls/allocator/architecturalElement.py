
from typing import Union, List, Dict, Tuple, Optional

from hwt.hdl.statements.statement import HdlStatement
from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwtHls.allocator.connectionsOfStage import ConnectionsOfStage, \
    extract_control_sig_of_interface, SignalsOfStages
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync, \
    HlsNetNodeReadSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtLib.handshaked.streamNode import StreamNode
from ipCorePackager.constants import INTF_DIRECTION
from hwtHls.clk_math import epsilon, start_clk


class AllocatorArchitecturalElement():
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type
    It is used as context for allocator.

    :ivar parentHls: parent HLS context for this element
    :ivar namePrefix: name prefix for debug purposes
    :ivar netNodeToRtl: dictionary {hls node: rtl instance}
    :ivar connections: list of connections in idividual stage in this arch. element, user for registration
        of products of nodes for sync generator
    :ivar allNodes: list in this arch element
    :ivar connections: list of rtl object allocated for each specific clock stage
    :ivar stageSignals: an object which makes connections list accessible by time
    :ivar interArchAnalysis: an object of inter architecture element sharing analysis which is set after allocation starts
    """

    def __init__(self, parentHls: "HlsPipeline", namePrefix:str,
                 allNodes: UniqList[HlsNetNode],
                 connections: List[ConnectionsOfStage],
                 stageSignals: SignalsOfStages):
        self.namePrefix = namePrefix
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
        self.connections = connections
        self.allNodes = allNodes
        assert isinstance(stageSignals, SignalsOfStages), stageSignals
        self.stageSignals = stageSignals
        self.interArchAnalysis: Optional["InterArchElementNodeSharingAnalysis"] = None

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        pass

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        con = self.connections[clkI]
        if intfDir == INTF_DIRECTION.MASTER:
            con.outputs.append(intf)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, intfDir
            con.inputs.append(intf)
        
    def instantiateHlsNetNodeOut(self, o: HlsNetNodeOut) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            clkI = start_clk(o.obj.scheduledOut[o.out_i], self.parentHls.clk_period)
            if len(self.stageSignals) <= clkI or self.stageSignals[clkI] is None:
                raise AssertionError("Asking for node output which should have forward declaration but it is missing", self, o, clkI)
            # new allocation, use registered automatically
            _o = o.obj.allocateRtlInstance(self)
            self._afterNodeInstantiated(o.obj, _o)
            if _o is None:
                # to support the return of the value directly to avoid lookup from dict
                try:
                    return self.netNodeToRtl[o]
                except KeyError:
                    # {v:k for k, v in o.obj.internOutToOut.items()}[o]
                    raise AssertionError(self, "Node did not instantiate its output", o.obj, o)
        else:
            # used and previously allocated
            # used_signals.getForTime(t).append(_o)
            pass

        return _o

    def instantiateHlsNetNodeOutInTime(self, o: HlsNetNodeOut, time:float,
                                       ) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        _o = self.instantiateHlsNetNodeOut(o)
        if isinstance(_o, TimeIndependentRtlResource):
            return _o.get(time)
        else:
            return _o

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
                   res_extraCond: Dict[Interface, TimeIndependentRtlResourceItem]):

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
                _o = onlySuc.allocateRtlInstance(self)  # to assert that the sync signal is constructed
                self._afterNodeInstantiated(onlySuc, _o)
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
                if intf == (1, 1):
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

    def allocateDataPath(self, iea: "InterArchElementNodeSharingAnalysis"):
        """
        Allocate main RTL object which are required from HlsNetNode instances assigned to this element.
        """
        raise NotImplementedError("Implement in child class")
    
    def allocateSync(self):
        """
        Instantiate an additional RTL objects to implement the synchronization of the element
        which are not direclty present in input HlsNetNode instances.
        """
        raise NotImplementedError("Implement in child class")
    
    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.namePrefix:s}>"

