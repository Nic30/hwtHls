
from typing import Union, List, Dict, Tuple, Optional

from hwt.code import SwitchLogic
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitsVal import BitsVal
from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    extractControlSigOfInterface, SignalsOfStages, ExtraCondMemberList, \
    SkipWhenMemberList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync, \
    HOrderingVoidT
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtLib.handshaked.streamNode import StreamNode
from ipCorePackager.constants import INTF_DIRECTION


class ArchElement():
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type
    It is used as context for allocator.

    :ivar netlist: parent HLS netlist context for this element
    :ivar namePrefix: name prefix for debug purposes
    :ivar netNodeToRtl: dictionary {HLS node: RTL instance}
    :ivar connections: list of connections in individual stage in this arch. element, user for registration
        of products of nodes for sync generator
    :ivar allNodes: list in this arch element
    :ivar connections: list of RTL object allocated for each specific clock stage
    :ivar stageSignals: an object which makes connections list accessible by time
    :ivar interArchAnalysis: an object of inter-architecture element sharing analysis which is set after allocation starts
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str,
                 allNodes: UniqList[HlsNetNode],
                 connections: List[ConnectionsOfStage],
                 stageSignals: SignalsOfStages):
        self.namePrefix = namePrefix
        self.netlist = netlist
        self.netNodeToRtl: Dict[
            Union[
                HlsNetNodeOut,  # any operation output
                Tuple[HlsNetNodeOut, Interface]  # write
            ],
            TimeIndependentRtlResource] = {}
        # function to create register/signal on RTL level
        self._reg = netlist.parentUnit._reg
        self._sig = netlist.parentUnit._sig
        self.connections = connections
        self.allNodes = allNodes
        assert isinstance(stageSignals, SignalsOfStages), stageSignals
        self.stageSignals = stageSignals
        self.interArchAnalysis: Optional["InterArchElementNodeSharingAnalysis"] = None

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        pass

    def _afterOutputUsed(self, o: HlsNetNodeOut):
        if o._dtype is HOrderingVoidT:
            return
        clkPeriod = self.netlist.normalizedClkPeriod
        epsilon = self.netlist.scheduler.epsilon
        depRtl = self.netNodeToRtl.get(o, None)
        if depRtl is not None:
            depRtl: TimeIndependentRtlResource
            if depRtl.timeOffset is INVARIANT_TIME:
                return
            # in in this arch. element
            # registers uses in new times
            t = depRtl.timeOffset + (len(depRtl.valuesInTime) - 1) * clkPeriod + epsilon
            # :note: done in reverse so we do not have to always iterate over registered prequel
            for _ in reversed(depRtl.valuesInTime):
                sigs = self.stageSignals.getForTime(t)
                if depRtl in sigs:
                    break
                sigs.append(depRtl)
                t -= clkPeriod

    def _connectSync(self, con: ConnectionsOfStage, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        if intfDir == INTF_DIRECTION.MASTER:
            con.outputs.append(intf)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, intfDir
            con.inputs.append(intf)

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        con: ConnectionsOfStage = self.connections[clkI]
        return self._connectSync(con, intf, intfDir)

    def instantiateHlsNetNodeOut(self, o: HlsNetNodeOut) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            clkI = start_clk(o.obj.scheduledOut[o.out_i], self.netlist.normalizedClkPeriod)
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
            pass

        return _o

    def instantiateHlsNetNodeOutInTime(self, o: HlsNetNodeOut, time:float,
                                       ) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        _o = self.instantiateHlsNetNodeOut(o)
        if isinstance(_o, TimeIndependentRtlResource):
            return _o.get(time)
        else:
            res = self.netNodeToRtl.get(o, _o)
            if isinstance(res, TimeIndependentRtlResource):
                return res.get(time)
            return res

    def _copyChannelSync(self, intf: Interface,
                   node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                   extraSync: Optional[HlsNetNodeExplicitSync],
                   res_skipWhen: Dict[Interface, SkipWhenMemberList],
                   res_extraCond: Dict[Interface, ExtraCondMemberList]):

        if isinstance(node, HlsNetNodeRead):
            node: HlsNetNodeRead
            syncTime = node.scheduledOut[0]
        else:
            assert isinstance(node, (HlsNetNodeWrite, HlsNetNodeExplicitSync)), node
            syncTime = node.scheduledIn[0]

        if node.skipWhen is not None:
            e = node.dependsOn[node.skipWhen.in_i]
            skipWhen = self.instantiateHlsNetNodeOutInTime(e, syncTime)
        else:
            skipWhen = None

        if extraSync is not None and extraSync.skipWhen is not None:
            extraSkipWhen = self.instantiateHlsNetNodeOutInTime(extraSync.dependsOn[extraSync.skipWhen.in_i], syncTime)
            if skipWhen is None:
                skipWhen = extraSkipWhen
            else:
                skipWhen = TimeIndependentRtlResource(skipWhen.data | extraSkipWhen.data, syncTime, self).get(syncTime)

        if skipWhen is not None:
            curSkipWhen = res_skipWhen.get(intf, None)
            if curSkipWhen is not None:
                curSkipWhen.data.append(skipWhen)
            else:
                res_skipWhen[intf] = SkipWhenMemberList([skipWhen, ])
        
        if node.extraCond is not None:
            e = node.dependsOn[node.extraCond.in_i]
            extraCond = self.instantiateHlsNetNodeOutInTime(e, syncTime)
        else:
            extraCond = None
        
        if extraSync is not None and extraSync.extraCond is not None:
            extraExtraCond = self.instantiateHlsNetNodeOutInTime(extraSync.dependsOn[extraSync.extraCond.in_i], syncTime)
            if extraCond is None:
                extraCond = extraExtraCond
            else:
                extraCond = TimeIndependentRtlResource(extraCond.data & extraExtraCond.data, syncTime, self).get(syncTime)
        
        if extraCond is not None:
            curExtraCond = res_extraCond.get(intf, None)
            if curExtraCond is not None:
                curExtraCond.data.append((skipWhen, extraCond))
            else:
                extraCond = ExtraCondMemberList([(skipWhen, extraCond), ])
                res_extraCond[intf] = extraCond

    def _collectChannelRtlSync(self,
                          sync_per_io: Dict[Interface, Union[SkipWhenMemberList, ExtraCondMemberList]],
                          defaultVal: int):
        sync: Dict[Interface, RtlSignal] = {}
        for intf, sync_source in sync_per_io.items():
            intf = extractControlSigOfInterface(intf)
            if intf == (1, 1):
                # does not have any sync
                continue

            assert sync_source
            en = sync_source.resolve()
            if isinstance(en, BitsVal):
                # current block en=1
                assert int(en) == defaultVal, en
            else:
                assert isinstance(en, RtlSignal), en
                sync[intf] = en

        return sync

    def _makeSyncNode(self, prevStageDataVld: Optional[RtlSyncSignal], con: ConnectionsOfStage) -> StreamNode:
        masters = [extractControlSigOfInterface(intf) for intf in con.inputs]
        masters = [m for m in masters if not m == (1, 1)]
        slaves = [extractControlSigOfInterface(intf) for intf in con.outputs]
        slaves = [s for s in slaves if not s == (1, 1)]
        if not masters and not slaves:
            extraConds = None
            skipWhen = None
        else:
            # [todo]
            # * on HlsNetlist level replace all uses of every input data in skipWhen condition with data & vld mask
            # * on RtlNetlist level replace all uses of prev state reg. data in skipWhen condition in this cycle with data & prevStageDataVld mask
            #   * in this case if value is used in some later cycle in skipWhen condition it should be already anded from HlsNetlist level       
            # self._makeSyncNodeInjectInputVldToSkipWhenConditions(prevStageDataVld, con.syncIn, masters, slaves, con.io_skipWhen)
            extraConds = self._collectChannelRtlSync(con.io_extraCond, 1)
            skipWhen = self._collectChannelRtlSync(con.io_skipWhen, 0)

        sync = StreamNode(
            masters,
            slaves,
            extraConds=extraConds,
            skipWhen=skipWhen,
        )
        con.sync_node = sync
        return sync

    def _allocateIo(self, ioDiscovery: HlsNetlistAnalysisPassDiscoverIo, intf: Interface, node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                    con: ConnectionsOfStage,
                    ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                    ioSeen: UniqList[Interface],
                    rtl: List[HdlStatement]):
        assert rtl is not None
        ioSeen.append(intf)
        ioMuxes.setdefault(intf, []).append((node, rtl))

        # if it has some synchronization
        if isinstance(node, HlsNetNodeRead):
            con.inputs.append(intf)
        else:
            con.outputs.append(intf)

        self._copyChannelSync(intf, node, ioDiscovery.extraReadSync.get(node, None), con.io_skipWhen, con.io_extraCond)

    def _allocateIoMux(self, ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                             ioSeen: UniqList[Interface]):
        for io in ioSeen:
            muxCases = ioMuxes[io]
            if len(muxCases) == 1:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    yield muxCases[0][1]
                else:
                    assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
                    # no MUX needed and we already merged the synchronization
            else:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    # create a write MUX
                    rtlMuxCases = []
                    for w, stms in muxCases:
                        t = w.scheduledOut[0]
                        caseCond = None
                        if w.extraCond is not None:
                            caseCond = self.instantiateHlsNetNodeOutInTime(w.dependsOn[w.extraCond.in_i], t).data

                        if w.skipWhen is not None:
                            _caseCond = ~self.instantiateHlsNetNodeOutInTime(w.dependsOn[w.skipWhen.in_i], t).data
                            if caseCond is None:
                                caseCond = _caseCond
                            else:
                                caseCond = caseCond & _caseCond
                        assert caseCond is not None, ("Because write object do not have any condition it is not possible to resolve which value should be MUXed to output interface", muxCases[0][0].dst)
                        rtlMuxCases.append((caseCond, stms))
                    stms = rtlMuxCases[0][1]
                    if isinstance(stms, HdlAssignmentContainer):
                        defaultCase = stms.dst(None)
                    else:
                        defaultCase = [asig.dst(None) for asig in stms]
                    yield SwitchLogic(rtlMuxCases, default=defaultCase)
                else:
                    assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
                    # no MUX needed and we already merged the synchronization

    def allocateDataPath(self, iea: "InterArchElementNodeSharingAnalysis"):
        """
        Allocate main RTL object which are required from HlsNetNode instances assigned to this element.
        """
        raise NotImplementedError("Implement in child class")

    def allocateSync(self):
        """
        Instantiate an additional RTL objects to implement the synchronization of the element
        which are not directly present in input HlsNetNode instances.
        """
        raise NotImplementedError("Implement in child class")

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self.namePrefix:s}>"

