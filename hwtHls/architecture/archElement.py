
from copy import copy
from itertools import chain
from typing import Union, List, Dict, Tuple, Optional, Set

from hwt.code import SwitchLogic, And
from hwt.hdl.operator import Operator
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.value import HValue
from hwt.interfaces.std import HandshakeSync
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.interfaceLevel.interfaceUtils.utils import walkPhysInterfaces
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwt.synthesizer.rtlLevel.signalUtils.exceptions import SignalDriverErr
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    extractControlSigOfInterface, SignalsOfStages, ExtraCondMemberList, \
    SkipWhenMemberList, extractControlSigOfInterfaceTuple, SyncOfInterface, \
    InterfaceSyncTuple, getIntfSyncSignals
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
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

    def _afterOutputUsed(self, o: HlsNetNode):
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
            # for i in chain(con.inputs, con.outputs):
            #    sw = con.io_skipWhen.get(i, None)
            #    if sw is not None:
            #        sw: SkipWhenMemberList
            #        sw.data.append(TimeIndependentRtlResourceItem(None, intf.vld))

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

    # def _makeSyncNodeSearchSource(self, affectingSources: Dict[SyncOfInterface, Set[RtlSignal]],
    #                              syncIn: Optional[HandshakeSync], sig: RtlSignal):
    #    try:
    #        return affectingSources[sig]
    #    except KeyError:
    #        pass
    #    
    #    syncSet = None
    #    syncSetCreated = False
    #    d = sig.singleDriver()
    #    if isinstance(d, Operator):
    #        for o in d.operands:
    #            if isinstance(o, HValue):
    #                continue
    #            oSyncSet = self._makeSyncNodeSearchSource(affectingSources, syncIn, o)
    #        
    #            # to prevent unnecessary building and copy of dependency set
    #            if syncSet is None:
    #                syncSet = oSyncSet
    #            elif not syncSetCreated:
    #                syncSet = copy(syncSet)
    #                syncSetCreated = True
    #        
    #            syncSet.update(oSyncSet)
    #    else:
    #        assert isinstance(d, HdlStatement), d
    #        if syncIn is None:
    #            # assert isinstance(self, ArchElementFsm) or (isinstance(sig, RtlSyncSignal) and sig.def_val._is_full_valid()), (sig, "value of this signal must be initialized to a defined state")
    #            syncSet = set()
    #        else:
    #            syncSet = {syncIn, }
    #    
    #    affectingSources[sig] = syncSet
    #    return syncSet
   
    # def _makeSyncNodeResolveSyncDependenciesForSkipWhenConditions(self,
    #        prevStageDataVld: Optional[RtlSyncSignal],
    #        syncIn: Optional[HandshakeSync],
    #        masters: List[SyncOfInterface],
    #        slaves: List[SyncOfInterface],
    #        io_skipWhen: Dict[Interface, SkipWhenMemberList]) -> Dict[RtlSignal, Set[SyncOfInterface]]:
    #    """
    #    Collect every input signals and mark its synchronization interface to find out if the value of signal is valid. 
    #    """
    #    affectingSources: Dict[RtlSignal, Set[SyncOfInterface]] = {prevStageDataVld: set()}
    #    # discover boundary signals
    #    for i in chain(slaves, masters):
    #        if isinstance(i, tuple):
    #            intf = None
    #            for sig in i:
    #                if isinstance(sig, Interface):
    #                    intf = sig._parent
    #                    assert intf is not None, sig
    #                    break
    #                elif isinstance(sig, (int, HValue)):
    #                    pass
    #                else:
    #                    raise NotImplementedError()
    #            if intf is None:
    #                continue
    #        else:
    #            intf = i
    #        syncSignals = getIntfSyncSignals(intf)
    #        for sig in walkPhysInterfaces(intf):
    #            if any((x is sig) for x in syncSignals):
    #                # sync itself
    #                affectingSources[sig._sig] = {}
    #            else:
    #                # data
    #                affectingSources[sig._sig] = {i, }
    #
    #    for i in masters:
    #        if isinstance(i, InterArchElementHandshakeSync):
    #            for _, dst in i.data:
    #                dst: TimeIndependentRtlResourceItem
    #                assert dst.data not in affectingSources, (dst.data, i, affectingSources, affectingSources[dst.data])
    #                affectingSources[dst.data] = {i, }
    #
    #    # for every skipWhen condition resolve its sync. dependencies
    #    for intf in chain(masters, slaves):
    #        intfSkipWhen = io_skipWhen.get(intf, None)
    #        
    #        if intfSkipWhen is None or not intfSkipWhen.data:
    #            # this interface does not have skip when condition
    #            continue
    #        for sw in intfSkipWhen.data:
    #            #if sw.parent is not None and len(sw.parent.valuesInTime) > 1:
    #            #    # if this is a register, this data comes from previous stage
    #            #    syncSet = affectingSources.get(sw.data, None)
    #            #    if syncSet is None:
    #            #        syncSet = affectingSources[sw.data] = set()
    #            #
    #            #    if syncIn is not None:
    #            #        syncSet.add(syncIn)
    #            #    # else: assert isinstance(self, ArchElementFsm)
    #            #else:
    #            # we have to search the expression to find its source
    #            self._makeSyncNodeSearchSource(affectingSources, syncIn, sw.data)
    #
    #    return affectingSources

    # def _makeSyncNodeInjectInputVldRtlSignal(self, sig: RtlSignal,
    #                                              affectingSources: Dict[RtlSignal, Set[SyncOfInterface]],
    #                                              ackOfIntf: Dict[Interface, Union[RtlSignal, int]]):
    #    # we need to do data & vld input data immediately, because this condition is likely to specify the channel optionallity
    #    try:
    #        srcs = affectingSources[sig]
    #    except KeyError:
    #        return sig  # we do not know about affectingSources because signal is out of our scope
    #
    #    if len(srcs) < 1:
    #        # if there is just a single or static source the and with vld signal will be added later
    #        return sig
    #    else:
    #        # if this aggregates inputs from multiple sources add and with validity signal for each member
    #        # which does not already have it
    #        try:
    #            d = sig.singleDriver()
    #        except SignalDriverErr:
    #            if sig._dtype.bit_length() == 1:
    #                return sig & And(*(ackOfIntf[i] for i in srcs))
    #            else:
    #                raise NotImplementedError()
    #
    #        if isinstance(d, Operator):
    #            # if this originates from operator
    #            needRebuild = False
    #            newOperands = []
    #            for o in d.operands:
    #                oSrcs = affectingSources.get(o, None)
    #                if not oSrcs:
    #                    # the input is statically driven o outside of our scope
    #                    pass
    #
    #                else:
    #                    # we inject the vld of the interface
    #                    _o = self._makeSyncNodeInjectInputVldRtlSignal(o, affectingSources, ackOfIntf)
    #                    if o._dtype.bit_length() == 1:
    #                        if o is not _o:
    #                            newOperands.append(_o)
    #                            needRebuild = True
    #                            continue
    #
    #                newOperands.append(o)
    #
    #            if needRebuild:
    #                return d.operator._evalFn(*newOperands)
    #            else:
    #                return sig
    #        else:
    #            return sig & And(*(ackOfIntf[i] for i in srcs))
    #
    # def _makeSyncNodeInjectInputVldToSkipWhenList(self, intfSkipWhen: SkipWhenMemberList,
    #                                              affectingSources: Dict[RtlSignal, Set[SyncOfInterface]],
    #                                              ackOfIntf: Dict[Interface, Union[RtlSignal, int]]):
    #    for i, d in enumerate(intfSkipWhen.data):
    #        sig = self._makeSyncNodeInjectInputVldRtlSignal(d.data, affectingSources, ackOfIntf)
    #        if sig is not d.data:
    #            intfSkipWhen.data[i] = TimeIndependentRtlResourceItem(None, sig)
    #
    # def _makeSyncNodeInjectInputVldToSkipWhenConditions(self,
    #                                                    prevStageDataVld: Optional[RtlSyncSignal],
    #                                                    syncIn: Optional[HandshakeSync],
    #                                                    masters: List[SyncOfInterface],
    #                                                    slaves: List[SyncOfInterface],
    #                                                    io_skipWhen: Dict[Interface, SkipWhenMemberList]):
    #    # skipWhen conditions can depend on external data and validity of data in this stage
    #    # skipWhen condition can not be in undefined state because it would break the handshake synchonization
    #    # Because of this we need to and skipWhen condition with the signal which describes if it is valid.
    #    # To get this signal we need to walk the expression and find its sources.
    #    affectingSources = self._makeSyncNodeResolveSyncDependenciesForSkipWhenConditions(
    #        prevStageDataVld, syncIn, masters, slaves, io_skipWhen)
    #    ackOfIntf: Dict[Interface, Union[RtlSignal, int]] = {}
    #    for intf in masters:
    #        ack, _ = extractControlSigOfInterfaceTuple(intf)
    #        if isinstance(ack, int):
    #            assert ack == 1, ack
    #        ackOfIntf[intf] = ack
    #        
    #    for intf in slaves:
    #        _, ack = extractControlSigOfInterfaceTuple(intf)
    #        if isinstance(ack, int):
    #            assert ack == 1, ack
    #        ackOfIntf[intf] = ack
    #
    #    for intf in chain(masters, slaves):
    #        intfSkipWhen = io_skipWhen.get(intf, None)
    #        
    #        if intfSkipWhen is None or not intfSkipWhen.data:
    #            # this interface does not have skip when condition
    #            continue
    #        
    #        intfSkipWhen: SkipWhenMemberList
    #        self._makeSyncNodeInjectInputVldToSkipWhenList(intfSkipWhen, affectingSources, ackOfIntf)
    #        print(intf, intfSkipWhen.resolve())
    #        # # we have to extend intfSkipWhen condition
    #        # for otherIntfDir, otherIntf in chain(
    #        #        zip((INTF_DIRECTION.MASTER for _ in masters), masters),
    #        #        zip((INTF_DIRECTION.SLAVE for _ in slaves), slaves),
    #        #        ):
    #        #    isAffected = False
    #        #    for sw in intfSkipWhen.data:
    #        #        d = sw.data
    #        #        if isinstance(d, Interface):
    #        #            d = d._sig
    #        #        if otherIntf in affectingSources[d]:
    #        #            isAffected = True
    #        #            break
    #        #    if not isAffected:
    #        #        continue
    #        #
    #        #    # otherSkipWhen = io_skipWhen.get(otherIntf, None)
    #        #    isM = otherIntfDir == INTF_DIRECTION.MASTER
    #        #    otherIntfSync = extractControlSigOfInterfaceTuple(otherIntf)
    #        #    if isM:
    #        #        ack = otherIntfSync[0]
    #        #    else:
    #        #        ack = otherIntfSync[1]
    #        #
    #        #    if isinstance(ack, int):
    #        #        # always valid no otherSkipWhen or otherSkipWhen with no effect -> no extra sync required
    #        #        assert ack == 1, ack
    #        #    else:
    #        #        # [todo] collect ack, sw in advance
    #        #        # if otherSkipWhen is None or not otherSkipWhen.data:
    #        #            intfSkipWhen.data.append(TimeIndependentRtlResourceItem(None, ack))
    #        #        # else:
    #        #        #    otherSkipWhen: SkipWhenMemberList
    #        #        #    sw = otherSkipWhen.resolve()
    #        #        #    intfSkipWhen.data.append(TimeIndependentRtlResourceItem(None, ack | (~ack & sw)))
    #        #             
    #        # print(intf)
    #        # print(intfSkipWhen)
    #        # print("")
    #
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
