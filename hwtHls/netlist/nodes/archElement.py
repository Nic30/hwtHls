
from typing import Union, List, Dict, Tuple, Optional, Generator

from hwt.code import SwitchLogic
from hwt.code_utils import rename_signal
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.value import HValue
from hwt.interfaces.std import HandshakeSync, Signal
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    extractControlSigOfInterface, SignalsOfStages, ExtraCondMemberList, \
    SkipWhenMemberList
from hwtHls.architecture.interArchElementHandshakeSync import InterArchElementHandshakeSync
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.orderable import HdlType_isVoid, HVoidOrdering
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtLib.handshaked.streamNode import StreamNode, _get_valid_signal, \
    _get_ready_signal, INTERFACE_OR_VLD_RD_TUPLE
from ipCorePackager.constants import INTF_DIRECTION


class ArchElement():
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type.
    This group of nodes usually corresponds to a IO cluster of to set of IO clusters.
    Main purpose of this object is:

    * Precise inter element communication specification
    * Context during RTL allocation
    * Synchronization type specification

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
        self._private_interfaces = netlist.parentUnit._private_interfaces
        self.connections = connections
        self.allNodes = allNodes
        assert isinstance(stageSignals, SignalsOfStages), stageSignals
        self.stageSignals = stageSignals
        self.interArchAnalysis: Optional["InterArchElementNodeSharingAnalysis"] = None
        self._dbgAddNamesToSyncSignals = False
        self._dbgExplicitlyNamedSyncSignals = set()
        self._beginClkI: Optional[int] = None
        self._endClkI: Optional[int] = None

    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        """
        Iterate slots for clock windows which are containing scheduled nodes in this element.
        """
        raise NotImplementedError("Implement this method in child class", self)

    def getStageForClock(self, clkIndex: int) -> List[HlsNetNode]:
        """
        Get clock window slot for a specified clock index.
        """
        raise NotImplementedError("Implement this method in child class", self)

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        pass

    def _afterOutputUsed(self, o: HlsNetNodeOut):
        if HdlType_isVoid(o._dtype):
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

    def _connectSync(self, clkI: int, con: ConnectionsOfStage, intf: InterArchElementHandshakeSync, intfDir: INTF_DIRECTION, isBlocking: bool):
        if intfDir == INTF_DIRECTION.MASTER:
            con.outputs.append((intf, isBlocking))
            ioNode = HlsNetNodeWrite(self.netlist, None, intf, name=intf._name)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, intfDir
            con.inputs.append((intf, isBlocking))
            if not intf.data:
                dtype = HVoidOrdering
            else:
                raise NotImplementedError()
            ioNode = HlsNetNodeRead(self.netlist, intf, dtype=dtype, name=intf._name)

        self.getStageForClock(clkI).append(ioNode)
        return ioNode

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION, isBlocking: bool):
        assert self._beginClkI is None or clkI >= self._beginClkI, (
            "can not add sync for clock slot which does not exist in this element", self, self._beginClkI, clkI)
        assert self._endClkI is None or clkI <= self._endClkI, (
            "can not add sync for clock slot which does not exist in this element", self, self._endClkI, clkI)

        con: ConnectionsOfStage = self.connections[clkI]
        self._connectSync(clkI, con, intf, intfDir, isBlocking)
        return con

    def instantiateHlsNetNodeOut(self, o: HlsNetNodeOut) -> TimeIndependentRtlResource:
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            if o.obj not in self.allNodes:
                if HdlType_isVoid(o._dtype):
                    return []

            clkI = start_clk(o.obj.scheduledOut[o.out_i], self.netlist.normalizedClkPeriod)
            if len(self.stageSignals) <= clkI or self.stageSignals[clkI] is None:
                raise AssertionError("Asking for node output which should have forward declaration but it is missing", self, o, clkI)
            # new allocation, use registered automatically
            _o = o.obj.allocateRtlInstance(self)
            self._afterNodeInstantiated(o.obj, _o)
            if (_o is None or not isinstance(_o, TimeIndependentRtlResource)) and not HdlType_isVoid(o._dtype):
                # to support the return of the value directly to avoid lookup from dict
                try:
                    res = self.netNodeToRtl[o]
                    assert isinstance(res, TimeIndependentRtlResource) and res.valuesInTime[0].data._dtype.bit_length() == o._dtype.bit_length(), (o, res, o._dtype, res.valuesInTime[0].data._dtype if  isinstance(res, TimeIndependentRtlResource) else None)
                    return res
                except KeyError:
                    raise AssertionError(self, "Node did not instantiate its output", o.obj, o)
        else:
            # used and previously allocated
            assert HdlType_isVoid(o._dtype) or (
                isinstance(_o, TimeIndependentRtlResource) and (
                 _o.valuesInTime[0].data._dtype == o._dtype or
                 _o.valuesInTime[0].data._dtype.bit_length() == o._dtype.bit_length()
                 )), (
                     o, _o, o._dtype,
                     _o.valuesInTime[0].data._dtype if isinstance(_o, TimeIndependentRtlResource) else None)
            pass

        return _o

    def instantiateHlsNetNodeOutInTime(self, o: HlsNetNodeOut, time:int,
                                       ) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        clkPeriod = self.netlist.normalizedClkPeriod
        assert self._beginClkI is None or time // clkPeriod >= self._beginClkI, (
            "object is not scheduled for this element", self, self._beginClkI, time, time // clkPeriod, o)
        assert self._endClkI is None or time // clkPeriod <= self._endClkI, (
            "object is not scheduled for this element", self, self._endClkI, time, time // clkPeriod, o)

        _o = self.instantiateHlsNetNodeOut(o)
        if isinstance(_o, TimeIndependentRtlResource):
            return _o.get(time)
        else:
            res = self.netNodeToRtl.get(o, _o)
            if isinstance(res, TimeIndependentRtlResource):
                return res.get(time)
            return res

    def instantiateHlsNetNodeInInTime(self, i: HlsNetNodeOut, time:int,
                                      ) -> TimeIndependentRtlResourceItem:
        return self.instantiateHlsNetNodeOutInTime(i.obj.dependsOn[i.in_i], time)

    def _andOptionalTimeIndependentRtlResourceItem(self,
                                                   a:Optional[TimeIndependentRtlResourceItem],
                                                   b:Optional[TimeIndependentRtlResourceItem],
                                                   syncTime: int):
        if a is None:
            if b is None:
                return None
            else:
                return b
        else:
            if b is None:
                return a
            else:
                res = b.data & a.data
                return TimeIndependentRtlResource(res, INVARIANT_TIME if isinstance(res, HValue) else syncTime, self, False).get(syncTime)

    def _orNegatedMaskedOptionalTimeIndependentRtlResourceItem(self,
                                                               a:Optional[TimeIndependentRtlResourceItem],
                                                               b:Optional[TimeIndependentRtlResourceItem],
                                                               bMask:Optional[TimeIndependentRtlResourceItem],
                                                               syncTime: int):
        """
        :return: a | (b & ~bMask) where every member can be None
        """
        if a is None:
            if bMask is None:
                if b is None:
                    return None
                else:
                    return b
            else:
                _a = b.data & ~bMask.data
        else:
            if bMask is None:
                _a = a.data | b.data
            else:
                _a = a.data | (b.data & ~bMask.data)

        return TimeIndependentRtlResource(_a, INVARIANT_TIME if isinstance(_a, HValue) else syncTime, self, False).get(syncTime)

    def _andNegatedMaskedOptionalTimeIndependentRtlResourceItem(self,
                                                                a:Optional[TimeIndependentRtlResourceItem],
                                                                b:Optional[TimeIndependentRtlResourceItem],
                                                                bMask:Optional[TimeIndependentRtlResourceItem],
                                                                syncTime: int):
        if a is None:
            if bMask is None:
                return b
            elif b is None:
                return None
            else:
                _a = b.data & ~bMask.data
        else:
            if bMask is None:
                if b is None:
                    return a
                else:
                    _a = a.data & b.data
            else:
                if b is None:
                    _a = a.data & ~bMask.data
                else:
                    _a = a.data & (b.data & ~bMask.data)
        return TimeIndependentRtlResource(_a, INVARIANT_TIME if isinstance(_a, HValue) else syncTime, self, False).get(syncTime)

    def _collectChannelSyncFromConcurrentSync(self,
                                              syncTime: int,
                                              parentSkipWhen: Optional[TimeIndependentRtlResourceItem],
                                              extraSyncs: UniqList[HlsNetNodeExplicitSync]
                                              ) -> Tuple[Optional[TimeIndependentRtlResourceItem], Optional[TimeIndependentRtlResourceItem]]:

        skipWhen = parentSkipWhen
        extraCond = None
        # for all extraSync on same level we have to:
        # skipWhen &= otherSkipWhern                    (skip if all sync allow skip)
        # extraCond |= otherExtraCond & ~otherSkipWhen  (1 if any condition is satisfied and not disabled)
        for extraSync in extraSyncs:
            extraSkipWhen = None
            if extraSync.skipWhen is not None:
                extraSkipWhen = self.instantiateHlsNetNodeInInTime(extraSync.skipWhen, syncTime)
                if self._dbgAddNamesToSyncSignals:
                    extraSkipWhen.data = rename_signal(self.netlist.parentUnit, extraSkipWhen.data, f"sync{extraSync._id}_skipWhen")
                    self._dbgExplicitlyNamedSyncSignals.add(extraSkipWhen.data)

                skipWhen = self._andOptionalTimeIndependentRtlResourceItem(skipWhen, extraSkipWhen, syncTime)

            if extraSync.extraCond is not None:
                # :note: we must not use skipWhen directly because it is "and" of all skipWhens and not just this skipWhen
                # _extraSkipWhen = self._andOptionalTimeIndependentRtlResourceItem(parentSkipWhen, extraSkipWhen, syncTime)
                extraExtraCond = self.instantiateHlsNetNodeInInTime(extraSync.extraCond, syncTime)
                if self._dbgAddNamesToSyncSignals:
                    extraExtraCond.data = rename_signal(self.netlist.parentUnit, extraExtraCond.data, f"sync{extraSync._id}_extraCond")
                    self._dbgExplicitlyNamedSyncSignals.add(extraExtraCond.data)

                extraCond = self._orNegatedMaskedOptionalTimeIndependentRtlResourceItem(
                    extraCond, extraExtraCond, extraSkipWhen, syncTime)

        return extraCond, skipWhen

    def _copyChannelSyncForElmInput(self, inputIntf: InterArchElementHandshakeSync, node: HlsNetNodeExplicitSync):
        syncTime = node.scheduledOut[0]
        if node.skipWhen is not None:
            e: HlsNetNodeOut = node.dependsOn[node.skipWhen.in_i]
            skipWhen = self.instantiateHlsNetNodeOutInTime(e, syncTime)
            self._afterOutputUsed(e)
            skipWhen = SkipWhenMemberList([skipWhen, ])
        else:
            skipWhen = None

        if node.extraCond is not None:
            e: HlsNetNodeOut = node.dependsOn[node.extraCond.in_i]
            extraCond = self.instantiateHlsNetNodeOutInTime(e, syncTime)
            self._afterOutputUsed(e)
            extraCond = ExtraCondMemberList([(skipWhen, extraCond), ])
        else:
            extraCond = None

        return extraCond, skipWhen

    def _copyChannelSync(self,
                   node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                   extraSyncs: Optional[UniqList[HlsNetNodeExplicitSync]],
                   curExtraCond:Optional[ExtraCondMemberList],
                   curSkipWhen: Optional[SkipWhenMemberList]):
        """
        Synchronization of channel is specified as a n-arry tree tuples (extraCond,skipWhen). Combination
        of these 2 bits specifies when then channel should be enabled and when its transaction is required.
        In addition each flag is optional on every level.

        :attention: This function is run for a single read/write node but there may be multiple such a nodes
            in a single clock period slot. Such a IO may be concurrent and thus skipWhen and extraCond must be merged.
        """

        # get time when IO happens
        if isinstance(node, HlsNetNodeRead):
            node: HlsNetNodeRead
            syncTime = node.scheduledOut[0]
        else:
            assert isinstance(node, (HlsNetNodeWrite, HlsNetNodeExplicitSync)), node
            syncTime = node.scheduledIn[0]

        if node.skipWhen is not None:
            e = node.dependsOn[node.skipWhen.in_i]
            topSkipWhen = self.instantiateHlsNetNodeOutInTime(e, syncTime)
            self._afterOutputUsed(e)
        else:
            topSkipWhen = None

        if node.extraCond is not None:
            e = node.dependsOn[node.extraCond.in_i]
            topExtraCond = self.instantiateHlsNetNodeOutInTime(e, syncTime)
            self._afterOutputUsed(e)
        else:
            topExtraCond = None

        if extraSyncs:
            extraCond, skipWhen = self._collectChannelSyncFromConcurrentSync(syncTime, topSkipWhen, extraSyncs)
        else:
            extraCond, skipWhen = None, topSkipWhen

        # (1 if top condition satisfied and any child condition is satisfied and not disabled)
        extraCond = self._andNegatedMaskedOptionalTimeIndependentRtlResourceItem(
            topExtraCond, extraCond, skipWhen, syncTime)

        if skipWhen is not None:
            if curSkipWhen is not None:
                curSkipWhen.data.append(skipWhen)
            else:
                curSkipWhen = SkipWhenMemberList([skipWhen, ])

        if extraCond is not None:
            if curExtraCond is not None:
                curExtraCond.data.append((skipWhen, extraCond))
            else:
                curExtraCond = ExtraCondMemberList([(skipWhen, extraCond), ])

        return curExtraCond, curSkipWhen

    def _collectChannelRtlSync(self,
                               syncPerIo: Dict[Interface, Union[SkipWhenMemberList, ExtraCondMemberList]],
                               defaultVal: int):
        sync: Dict[Interface, RtlSignal] = {}
        for intf, sync_source in syncPerIo.items():
            intf = extractControlSigOfInterface(intf)
            if intf == (1, 1):
                # does not have any sync
                continue

            assert sync_source
            en = sync_source.resolve()
            if isinstance(en, BitsVal):
                # current block en=1
                assert int(en) == defaultVal, (intf, en, "Enable condition is never satisfied, channel would be always dissabled")
            else:
                assert isinstance(en, RtlSignal), (intf, en)
                sync[intf] = en

        return sync

    def _modifySkipWhenForNonBlocking(self,
                                      io: INTERFACE_OR_VLD_RD_TUPLE,
                                      isBlocking: bool,
                                      ack: Union[RtlSignal, int, Signal],
                                      skipWhen: Optional[Dict[INTERFACE_OR_VLD_RD_TUPLE, RtlSignal]]) -> Optional[Dict[INTERFACE_OR_VLD_RD_TUPLE, RtlSignal]]:
        if not isBlocking and not isinstance(ack, int):
            if skipWhen is None:
                skipWhen = {}
            sw = skipWhen.get(io, None)
            if sw is None:
                sw = ~ack
            else:
                sw = sw | ~ack
            skipWhen[io] = sw

        return skipWhen

    def _makeSyncNodeDropSyncSignalForNonBlocking(self,
                                                  io: INTERFACE_OR_VLD_RD_TUPLE,
                                                  isInput: bool,
                                                  index: int,
                                                  ioList: List[Tuple[INTERFACE_OR_VLD_RD_TUPLE, bool]],
                                                  extraConds: Optional[Dict[INTERFACE_OR_VLD_RD_TUPLE, RtlSignal]],
                                                  skipWhen: Optional[Dict[INTERFACE_OR_VLD_RD_TUPLE, RtlSignal]]):
        vld = _get_valid_signal(io)
        rd = _get_ready_signal(io)
        if isInput:
            newIo = (1, rd)
        else:
            newIo = (vld, 1)

        ioList[index] = (newIo, False)
        if extraConds is not None:
            ec = extraConds.pop(io, None)
            if ec is not None:
                extraConds[newIo] = ec
        if skipWhen is not None:
            sw = skipWhen.pop(io, None)
            if sw is not None:
                skipWhen[newIo] = sw

    #def _finalizeSyncFlagsOfInterArchElementHandshakeSync(self,
    #                                                      con: ConnectionsOfStage,
    #                                                      masters: List[Tuple[INTERFACE_OR_VLD_RD_TUPLE, bool]],
    #                                                      slaves: List[Tuple[INTERFACE_OR_VLD_RD_TUPLE, bool]],
    #                                                      extraConds: Optional[Dict[INTERFACE_OR_VLD_RD_TUPLE, RtlSignal]],
    #                                                      skipWhen: Optional[Dict[INTERFACE_OR_VLD_RD_TUPLE, RtlSignal]]):
    #    # dissable output InterArchElementHandshakeSync if this state does not have ack
    #    for intf, _ in con.outputs:
    #        if isinstance(intf, InterArchElementHandshakeSync):
    #            # collect ack from all other IO channels
    #            conds = []
    #            for ((otherIo, _), d) in chain([(m, INTF_DIRECTION.MASTER) for m in masters],
    #                                           [(s, INTF_DIRECTION.SLAVE) for s in slaves]):
    #                if otherIo is intf:
    #                    continue
    #                if d == INTF_DIRECTION.MASTER:
    #                    en = _get_valid_signal(otherIo)
    #                else:
    #                    en = _get_ready_signal(otherIo)
    #                ec = None if extraConds is None else extraConds.get(otherIo, None)
    #                sw = None if skipWhen is None else skipWhen.get(otherIo, None)
    #                if ec is not None:
    #                    if en == 1:
    #                        en = ec
    #                    else:
    #                        en = en & ec
    #                if sw is not None:
    #                    if en == 1:
    #                        en = ~sw
    #                    else:
    #                        en = en & ~sw
    #                if en == 1:
    #                    continue
    #                conds.append(en)
    #
    #            if conds:
    #                if extraConds is None:
    #                    extraConds = {}
    #                extraCond = And(*conds)
    #                extraConds[intf] = extraCond
    #                skipWhen[intf] = ~extraCond
    #                
    #
    #    return extraConds, skipWhen
    #
    def _makeSyncNode(self, con: ConnectionsOfStage) -> StreamNode:
        masters = ((extractControlSigOfInterface(intf), isBlocking) for intf, isBlocking in con.inputs)
        slaves = ((extractControlSigOfInterface(intf), isBlocking) for intf, isBlocking in con.outputs)
        # ignore io without any sync
        masters = [m for m in masters if not m[0] == (1, 1)]
        slaves = [s for s in slaves if not s[0] == (1, 1)]

        if not masters and not slaves:
            extraConds = None
            skipWhen = None
        else:
            # [todo]
            # * on HlsNetlist level replace all uses of every input data in skipWhen condition with data & vld mask
            # * on RtlNetlist level replace all uses of prev. state reg. data in skipWhen condition in this cycle with data & prevStageDataVld mask
            #   * in this case if value is used in some later cycle in skipWhen condition it should be already anded from HlsNetlist level
            # self._makeSyncNodeInjectInputVldToSkipWhenConditions(prevStageDataVld, con.syncIn, masters, slaves, con.io_skipWhen)
            extraConds = self._collectChannelRtlSync(con.io_extraCond, 1)
            skipWhen = self._collectChannelRtlSync(con.io_skipWhen, 0)
            if self._dbgAddNamesToSyncSignals:
                extraConds = {io: rename_signal(self.netlist.parentUnit, cond, f"{io._name}_extraCond")
                              for io, cond in extraConds.items()}
                skipWhen = {io: rename_signal(self.netlist.parentUnit, cond, f"{io._name}_skipWhen")
                            for io, cond in skipWhen.items()}
                for d in (extraConds, skipWhen):
                    self._dbgExplicitlyNamedSyncSignals.update(d.values())

        for i, (m, isBlocking) in enumerate(masters):
            if not isBlocking:
                self._makeSyncNodeDropSyncSignalForNonBlocking(m, True, i, masters, extraConds, skipWhen)

        for i, (s, isBlocking) in enumerate(slaves):
            if not isBlocking:
                self._makeSyncNodeDropSyncSignalForNonBlocking(s, False, i, masters, extraConds, skipWhen)

        #extraConds, skipWhen = self._finalizeSyncFlagsOfInterArchElementHandshakeSync(con, masters, slaves, extraConds, skipWhen)

        sync = StreamNode(
            [m for m, _ in masters],  # rm isBlocking flags
            [s for s, _ in slaves],
            extraConds=extraConds,
            skipWhen=skipWhen,
        )
        con.sync_node = sync
        return sync

    def _allocateIo(self, ioDiscovery: HlsNetlistAnalysisPassIoDiscover,
                    intf: Interface,
                    node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                    con: ConnectionsOfStage,
                    ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                    ioSeen: UniqList[Interface],
                    rtl: List[HdlStatement]):
        assert rtl is not None
        ioSeen.append(intf)
        ioMuxes.setdefault(intf, []).append((node, rtl))

        # if it has some synchronization
        if isinstance(node, HlsNetNodeRead):
            con.inputs.append((intf, node._isBlocking))
        else:
            con.outputs.append((intf, node._isBlocking))

        curExtraCond = con.io_extraCond.get(intf, None)
        curSkipWhen = con.io_skipWhen.get(intf, None)
        curExtraCond, curSkipWhen = self._copyChannelSync(node,
                                        ioDiscovery.extraReadSync.get(node, None),
                                        curExtraCond,
                                        curSkipWhen)
        if curExtraCond is not None:
            con.io_extraCond[intf] = curExtraCond
        if curSkipWhen is not None:
            con.io_skipWhen[intf] = curSkipWhen

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


ArchElmEdge = Tuple[ArchElement, ArchElement]
