from typing import Union, List, Dict, Tuple, Optional, Generator, Literal, Set

from hwt.code import SwitchLogic
from hwt.code_utils import rename_signal
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.statements.assignmentContainer import HdlAssignmentContainer
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hdl.const import HConst
from hwt.hwIOs.std import HwIOSignal
from hwt.pyUtils.setList import SetList
from hwt.hwIO import HwIO
from hwt.mainBases import HwIOBase
from hwt.constants import NOT_SPECIFIED
from hwt.mainBases import RtlSignalBase
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwt.synthesizer.rtlLevel.rtlSyncSignal import RtlSyncSignal
from hwt.hwModule import HwModule
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    ExtraCondMemberList, SkipWhenMemberList, \
    InterfaceOrReadWriteNodeOrValidReadyTuple, IORecord, ConnectionsOfStageList
from hwtHls.architecture.syncUtils import HwIO_getSyncTuple
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk, indexOfClkPeriod
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwt.pyUtils.typingFuture import override
from hwtLib.handshaked.streamNode import StreamNode, HwIOOrValidReadyTuple, \
    ValidReadyTuple
from hwtLib.logic.rtlSignalBuilder import RtlSignalBuilder


class ArchElement(HlsNetNodeAggregate):
    """
    An element which represents a group of netlist nodes synchronized by same synchronization type.
    This group of nodes usually corresponds to a IO cluster of to set of IO clusters.
    Main purpose of this object is:

    * Precise inter element communication specification
    * Context during RTL allocation
    * Synchronization type specification

    :ivar netNodeToRtl: dictionary {HLS node: RTL instance}
    :ivar connections: list of connections in individual stages in this arch. element, used for registration
        of products of nodes for sync generator
    :ivar connections: list of RTL object allocated for each specific clock stage
    :ivar _rtlDatapathAllocated: flag which is True if datapath logic was already allocated in RTL
    :ivar _rtlSyncAllocated: flag which is True if synchronization logic was already allocated in RTL
    :ivar _beginClkI: index of the first non-empty stage
    :ivar _endClkI: index of the last non-empty stage
    :ivar _dbgAddSignalNamesToSync: :see: :class:`HlsNetlistCtx`
    :ivar _dbgAddSignalNamesToData: :see: :class:`HlsNetlistCtx`
    
    :attention: The ArchElement must work no matter what nodes are inside.
        Due to resource limitations fragments of circuits may be merged
        into ArchElement in arbitrary way.
        This is important in cases where channel communication is used.
        HlsNetNodeWriteForwardedge and HlsNetNodeReadForwardedge may appear in the same stage
        within the same element
    """

    def __init__(self, netlist: "HlsNetlistCtx", name:str,
                 subNodes: SetList[HlsNetNode],
                 connections: ConnectionsOfStageList):
        HlsNetNodeAggregate.__init__(self, netlist, subNodes, name)
        self.netlist = netlist
        self.netNodeToRtl: Dict[
            Union[
                HlsNetNodeOut,  # any operation output
                Tuple[HlsNetNodeOut, HwIO]  # write
            ],
            TimeIndependentRtlResource] = {}
        # function to create register/signal on RTL level
        self.connections = connections
        self._dbgAddSignalNamesToSync = netlist._dbgAddSignalNamesToSync
        self._dbgAddSignalNamesToData = netlist._dbgAddSignalNamesToData
        self._dbgExplicitlyNamedSyncSignals = set()
        self._beginClkI: Optional[int] = None
        self._endClkI: Optional[int] = None
        self._rtlDatapathAllocated: bool = False
        self._rtlSyncAllocated: bool = False

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = HlsNetNodeAggregate.clone(self, memo, keepTopPortsConnected)
        if isNew:
            for cos in self.connections:
                assert cos.isUnused()
            y.connections = ConnectionsOfStageList(y.netlist.normalizedClkPeriod,
                                                   initVals=(ConnectionsOfStage(y, c.clkIndex)
                                                             if c is not None else None
                                                             for c in self.connections))
        return y, isNew

    def _reg(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             clk: Union[RtlSignalBase, None, Tuple[RtlSignalBase, HOperatorDef]]=None,
             rst: Optional[RtlSignalBase]=None,
             nextSig:Optional[RtlSignalBase]=NOT_SPECIFIED) -> RtlSyncSignal:
        """
        :see: :meth:`hwt.synthesizer.interfaceLevel.hwModuleImplHelpers._reg`
        """
        return self.netlist.parentHwModule._reg(name, dtype=dtype, def_val=def_val, clk=clk, rst=rst, nextSig=nextSig)

    def _sig(self, name: str,
             dtype: HdlType=BIT,
             def_val: Union[int, None, dict, list]=None,
             nop_val: Union[int, None, dict, list, "NOT_SPECIFIED"]=NOT_SPECIFIED) -> RtlSignal:
        """
        :see: :meth:`hwt.synthesizer.interfaceLevel.hwModuleImplHelpers._sig`
        """
        return self.netlist.parentHwModule._sig(name, dtype=dtype, def_val=def_val, nop_val=nop_val)

    @override
    def _addOutput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeOut, HlsNetNodeIn]:
        outerO, internI = super(ArchElement, self)._addOutput(t, name, time=time)
        if time is not None:
            clkIndex = indexOfClkPeriod(time, self.netlist.normalizedClkPeriod)
            self._addNodeIntoScheduled(clkIndex, internI.obj)
        return outerO, internI

    @override
    def _addInput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeIn, HlsNetNodeOut]:
        outerI, internO = super(ArchElement, self)._addInput(t, name, time=time)
        if time is not None:
            clkIndex = indexOfClkPeriod(time, self.netlist.normalizedClkPeriod)
            self._addNodeIntoScheduled(clkIndex, internO.obj)
        return outerI, internO

    @override
    def _removeInput(self, index:int):
        inInside = self._inputsInside[index]
        if inInside.scheduledOut is not None:
            clkPeriod = self.netlist.normalizedClkPeriod
            clkI = inInside.scheduledOut[0] // clkPeriod
            self.getStageForClock(clkI).remove(inInside)

        HlsNetNodeAggregate._removeInput(self, index)

    @override
    def _removeOutput(self, index:int):
        outInside = self._outputsInside[index]
        if outInside.scheduledIn is not None:
            clkPeriod = self.netlist.normalizedClkPeriod
            clkI = outInside.scheduledIn[0] // clkPeriod
            self.getStageForClock(clkI).remove(outInside)

        HlsNetNodeAggregate._removeOutput(self, index)

    @override
    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False):
        super(ArchElement, self).filterNodesUsingSet(removed, recursive=recursive)
        for _, state in self.iterStages():
            state[:] = (n for n in state if n not in removed)

    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        """
        Iterate slots for clock windows which are containing scheduled nodes in this element.
        """
        raise NotImplementedError("Implement this method in child class", self)

    def getStageForTime(self, time: SchedTime) -> List[HlsNetNode]:
        assert time >= 0, time
        return self.getStageForClock(time // self.netlist.normalizedClkPeriod)

    def getStageForClock(self, clkIndex: int) -> List[HlsNetNode]:
        """
        Get clock window slot for a specified clock index.
        """
        raise NotImplementedError("Implement this method in child class", self)

    def _addNodeIntoScheduled(self, clkI: int, node: HlsNetNode):
        """
        :attention: It is expected that the node itself is already scheduled
        """
        if self._beginClkI is not None and clkI < self._beginClkI:
            self._beginClkI = clkI
        if clkI >= len(self.connections):
            for _ in range(len(self.connections) - 1, clkI + 1):
                self.connections.append(ConnectionsOfStage(self, len(self.connections)))

        if self.connections[clkI] is None:
            self.connections[clkI] = ConnectionsOfStage(self, clkI)
        e = self._endClkI
        if self._endClkI is not None and e < clkI:
            self._endClkI = clkI

        self.getStageForClock(clkI).append(node)
        self._subNodes.append(node)

    @override
    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)  # ports do not have any extra delay

    def addImplicitSyncChannelsInsideOfElm(self):
        """
        Create HlsNetNodeReadForwardedge/HlsNetNodeWriteForwardedge pairs to implement synchronization
        between parts of this element.
        """
        pass

    @override
    def rtlStatesMayHappenConcurrently(self, stateClkI0: int, stateClkI1: int):
        raise NotImplementedError()

    def rtlRegisterOutputRtlSignal(self,
                                   outOrTime: Union[HlsNetNodeOut, SchedTime],
                                   data: Union[RtlSignal, HwIO, HConst],
                                   isExplicitRegister: bool,
                                   isForwardDeclr: bool,
                                   mayChangeOutOfCfg: bool,
                                   timeOffset: Union[SchedTime, Literal[INVARIANT_TIME, NOT_SPECIFIED]]=NOT_SPECIFIED):
        """
        Construct the container for RtlSignal and alike which is used for resolving of synchronization for it.
        """
        notAddToNetNodeToRtl = isinstance(outOrTime, SchedTime) or outOrTime is NOT_SPECIFIED
        timeOffset = \
            timeOffset if timeOffset is not NOT_SPECIFIED else\
            INVARIANT_TIME if (isinstance(data, HConst) or isinstance(data, RtlSignal) and data._const) else\
            outOrTime if notAddToNetNodeToRtl else\
            outOrTime.obj.scheduledOut[outOrTime.out_i]

        if not notAddToNetNodeToRtl:
            curTir = self.netNodeToRtl.get(outOrTime, None)
            if curTir is not None:
                curTir: TimeIndependentRtlResource
                assert curTir.isForwardDeclr, ("Only forward declarations may be redefined", curTir)
                dataSig = curTir.valuesInTime[0].data
                assert not dataSig.drivers, ("The signal should be forward declaration and this should be its only driver", dataSig)
                assert curTir.timeOffset == timeOffset or timeOffset == INVARIANT_TIME, (curTir, curTir.timeOffset, timeOffset)
                assert curTir.allocator is self, (curTir, curTir.allocator, self)
                assert dataSig is not data, data
                dataSig(data)
                curTir.isForwardDeclr = False
                return curTir

        tir = TimeIndependentRtlResource(data, timeOffset, self, isExplicitRegister, isForwardDeclr, mayChangeOutOfCfg)
        if not notAddToNetNodeToRtl:
            self.netNodeToRtl[outOrTime] = tir

        return tir

    def rtlAllocHlsNetNodeOut(self, o: HlsNetNodeOut) -> TimeIndependentRtlResource:
        """
        Allocate all RTL which is represented by provided output
        """
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            if HdlType_isVoid(o._dtype):
                return []
            
            assert not o.obj._isRtlAllocated, (
                "Node was allocated, but the output rtl is missing, this could be the case only for outputs of void type, "
                "This error could be also a sign of node being allocated/used directly in other element (without port on this element)", o)

            clkI = start_clk(o.obj.scheduledOut[o.out_i], self.netlist.normalizedClkPeriod)
            if len(self.connections) <= clkI or self.connections[clkI] is None:
                raise AssertionError("Asking for node output which should have forward declaration but it is missing", self, o, clkI)
            # new allocation, use registered automatically
            assert not o.obj._isRtlAllocated, (o, "if rtl is allocated the output should already had the rlt in netNodeToRtl")
            _o = o.obj.rtlAlloc(self)
            assert o.obj._isRtlAllocated, o
            if (_o is None or not isinstance(_o, TimeIndependentRtlResource)) and not HdlType_isVoid(o._dtype):
                # to support the return of the value directly to avoid lookup from dict
                try:
                    res = self.netNodeToRtl[o]
                    assert isinstance(res, TimeIndependentRtlResource) and \
                        (not isinstance(o._dtype, HBits) or\
                         res.valuesInTime[0].data._dtype.bit_length() == o._dtype.bit_length()), (
                             o, res, o._dtype, res.valuesInTime[0].data._dtype
                             if isinstance(res, TimeIndependentRtlResource) else None)
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

        return _o

    def rtlAllocHlsNetNodeOutInTime(self, o: HlsNetNodeOut, time:int,
                                       ) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        """
        :meth:`~.rtlAllocHlsNetNodeOut` method with also gets the RTL resorce in specified time.
        """
        clkPeriod = self.netlist.normalizedClkPeriod
        assert self._beginClkI is None or time // clkPeriod >= self._beginClkI, (
            "object is not scheduled for this element", self, self._beginClkI, time, time // clkPeriod, o)
        assert self._endClkI is None or time // clkPeriod <= self._endClkI, (
            "object is not scheduled for this element", self, self._endClkI, time, time // clkPeriod, o)

        _o = self.rtlAllocHlsNetNodeOut(o)
        if isinstance(_o, TimeIndependentRtlResource):
            assert _o.allocator is self, (o, _o, _o.allocator, self)
            return _o.get(time)
        else:
            res = self.netNodeToRtl.get(o, _o)
            if isinstance(res, TimeIndependentRtlResource):
                assert res.allocator is self, (o, res, res.allocator, self)
                return res.get(time)
            return res

    def rtlAllocHlsNetNodeInInTime(self, i: HlsNetNodeOut, time:int,
                                      ) -> TimeIndependentRtlResourceItem:
        return self.rtlAllocHlsNetNodeOutInTime(i.obj.dependsOn[i.in_i], time)

    def rtlAllocDatapathRead(self, node: HlsNetNodeRead, con: ConnectionsOfStage, rtl: List[HdlStatement],
                             validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
        """
        :attention: :see: :meth:`~._rtlAllocDatapathIo`
        """
        self._rtlAllocDatapathIo(node.src, node, con, rtl, True, validHasCustomDriver, readyHasCustomDriver)

    def rtlAllocDatapathWrite(self, node: HlsNetNodeWrite, con: ConnectionsOfStage, rtl: List[HdlStatement],
                              validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
        """
        :attention: :see: :meth:`~._rtlAllocDatapathIo`
        """
        self._rtlAllocDatapathIo(node.dst, node, con, rtl, False, validHasCustomDriver, readyHasCustomDriver)

    def _rtlAllocDatapathIo(self,
                    hwIO: Optional[HwIO],
                    node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                    con: ConnectionsOfStage,
                    rtl: List[HdlStatement],
                    isRead: bool,
                    validHasCustomDriver:bool,
                    readyHasCustomDriver:bool):
        """
        There may be multiple read/write instances accessing the same hw interface in this ConnectionsOfStage.
        If this is the case it is proven that the access is concurrent.
        Because of this we first have to see all nodes in stage before resolving enable conditions for hw interface.

        :attention: validHasCustomDriver are related to IO and must be set always the same when calling this method multiple times for this IO
        """
        assert isinstance(rtl, list), (node, rtl.__class__, rtl)
        if hwIO is None:
            assert not node._rtlUseValid and not node._rtlUseReady, node
            valid = 1
            ready = 1
            validReadyPhysicallyPresent = (1, 1)
            if isRead:
                assert HdlType_isVoid(node._outputs[0]._dtype), ("Node without any hw HwIO or sync must not have any data", node)
                if isinstance(node, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)):
                    hwIO = node.associatedWrite
            else:
                assert HdlType_isVoid(node.dependsOn[0]._dtype), ("Node without any hw HwIO or sync must not have any data", node)
            # we need some object to store extraCond and skipWhen
        else:
            assert isinstance(hwIO, (HwIO, RtlSignalBase)), ("Node should already have interface resolved", node, hwIO)
            validReadyPhysicallyPresent = HwIO_getSyncTuple(hwIO)
            valid, ready = validReadyPhysicallyPresent

            if isinstance(node, (HlsNetNodeReadForwardedge, HlsNetNodeWriteForwardedge)):
                if not node._rtlUseReady:
                    ready = 1

                if not node._rtlUseValid:
                    valid = 1

            if isRead:
                if not node._isBlocking:
                    valid = 1  # rm valid from sync because we do not have to wait for it
                if not node._rtlUseReady:
                    ready = 1
            else:
                if not node._isBlocking:
                    ready = 1  # rm ready from sync because we do not have to wait for it
                if not node._rtlUseValid:
                    valid = 1
        # rm ready/valid from sync as it will be driven only form node flags instead from StreamNode
        if not isRead and node.hasValidOnlyToPassFlags():
            valid = 1
        if isRead and node.hasReadyOnlyToPassFlags():
            ready = 1

        if isRead:
            ioContainer = con.inputs
        else:
            ioContainer = con.outputs

        validReadyForSync = (valid, ready)

        if valid == 1 and ready == 1:
            if hwIO is None:
                keyForFlagDicts = node
            else:
                keyForFlagDicts = hwIO
        else:
            keyForFlagDicts = validReadyForSync

        assert keyForFlagDicts is not None and\
               not (isinstance(keyForFlagDicts , tuple) and\
                    keyForFlagDicts == (1, 1)), node

        io = IORecord(node, hwIO, validReadyForSync, keyForFlagDicts, validReadyPhysicallyPresent,
                      validHasCustomDriver, readyHasCustomDriver)
        ioContainer.append(io)

        if hwIO is None:
            assert not rtl, ("If it has no HW interface (it is only virtual read/write)"
                             " it should not produce any rtl", node)
        else:
            muxVariants = con.ioMuxes.get(hwIO, None)
            if muxVariants is None:
                con.ioMuxesKeysOrdered.append(hwIO)
                muxVariants = con.ioMuxes[hwIO] = []
            muxVariants.append((node, rtl))

        if isRead:
            assert keyForFlagDicts not in con.outputs_extraCond, node
            assert keyForFlagDicts not in con.outputs_skipWhen, node
            io_extraCond = con.inputs_extraCond
            io_skipWhen = con.inputs_skipWhen
        else:
            assert keyForFlagDicts not in con.inputs_extraCond, node
            assert keyForFlagDicts not in con.inputs_skipWhen, node
            io_extraCond = con.outputs_extraCond
            io_skipWhen = con.outputs_skipWhen

        self._rtlAllocDatapathAddIoToConnections(node, isRead, keyForFlagDicts, validReadyForSync,
                                                 io_extraCond, io_skipWhen)

    def _rtlAllocDatapathAddIoToConnections(self,
                   node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                   isRead: bool,
                   keyForFlagDicts: InterfaceOrReadWriteNodeOrValidReadyTuple,
                   validReadyTupleUsedInSyncGeneration: ValidReadyTuple,
                   io_extraConds: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, ExtraCondMemberList],
                   io_skipWhens: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, SkipWhenMemberList]):
        """
        Add io extraCond, skipWhen flag to io_extraConds, io_skipWhens dictionaries

        :attention: This function is run for a single read/write node but there may be multiple such nodes
            in a single clock period slot. Such a IO may be concurrent and thus skipWhen and extraCond must be merged.
        """

        # get time when IO happens
        if isRead:
            node: HlsNetNodeRead
            syncTime = node.scheduledOut[0]
        else:
            assert isinstance(node, HlsNetNodeWrite), node
            syncTime = node.scheduledIn[0]

        skipWhen = node.skipWhen
        if skipWhen is not None:
            syncTime = node.scheduledIn[skipWhen.in_i]
            e = node.dependsOn[skipWhen.in_i]
            skipWhen = self.rtlAllocHlsNetNodeOutInTime(e, syncTime).data

        extraCond = node.extraCond
        if extraCond is not None:
            syncTime = node.scheduledIn[extraCond.in_i]
            e = node.dependsOn[extraCond.in_i]
            extraCond = self.rtlAllocHlsNetNodeOutInTime(e, syncTime).data
            if isRead:
                ack = validReadyTupleUsedInSyncGeneration[0]
            else:
                ack = validReadyTupleUsedInSyncGeneration[1]

            if extraCond is ack:
                extraCond = None  # it is useless to use this twice

        if skipWhen is not None:
            curSkipWhen = io_skipWhens.get(keyForFlagDicts, None)
            if curSkipWhen is not None:
                curSkipWhen.data.append(skipWhen)
            else:
                curSkipWhen = SkipWhenMemberList([skipWhen, ])
                io_skipWhens[keyForFlagDicts] = curSkipWhen

        if extraCond is not None:
            curExtraCond = io_extraConds.get(keyForFlagDicts, None)
            if curExtraCond is not None:
                curExtraCond.data.append((skipWhen, extraCond))
            else:
                curExtraCond = ExtraCondMemberList([(skipWhen, extraCond), ])
                io_extraConds[keyForFlagDicts] = curExtraCond

    def _rtlAllocDatapathGetIoAck(self, node: Union[HlsNetNodeRead, HlsNetNodeWrite], namePrefix:str) -> Optional[RtlSignal]:
        """
        Use extraCond, skipWhen condition to get enable condition.
        """
        ack = None
        extraCond = node.getExtraCondDriver()
        if extraCond is not None:
            ack = self.rtlAllocHlsNetNodeOutInTime(extraCond, node.scheduledIn[node.extraCond.in_i]).data

        skipWhen = node.getSkipWhenDriver()
        if skipWhen is not None:
            _skip = self.rtlAllocHlsNetNodeOutInTime(skipWhen, node.scheduledIn[node.skipWhen.in_i]).data
            ack = RtlSignalBuilder.buildOrNegatedMaskOptional(ack, _skip)

        if isinstance(ack, HBitsConst):
            assert int(ack) == 1, (node, "If ack=0 this means that channel is always stalling")
            ack = None

        if ack is not None and self._dbgAddSignalNamesToSync:
            ack = rename_signal(self.netlist.parentHwModule, ack, f"{namePrefix:s}n{node._id}_ack")

        return ack

    def _rtlChannelSyncFinalizeFlag(self, parentHwModule: HwModule,
                                    flagDict: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, Union[ExtraCondMemberList, SkipWhenMemberList]],
                                    flagsDictKey: InterfaceOrReadWriteNodeOrValidReadyTuple,
                                    baseName:Optional[str],
                                    flagName:Optional[str],
                                    defaultVal: int) -> Optional[RtlSignal]:
        flagBundle = flagDict.get(flagsDictKey, None)
        if flagBundle is None or not flagBundle:
            return None
        flag = flagBundle.resolve()
        if flag is None:
            return None
        elif isinstance(flag, HBitsConst):
            assert int(flag) == defaultVal, (baseName, flagName, flag, "Enable condition is never satisfied, channel would be always disabled")
            return None
        else:
            assert isinstance(flag, (RtlSignal, HwIOSignal)), (baseName, flagName, flag)
            if self._dbgAddSignalNamesToSync and baseName is not None and baseName is not flagName:
                newName = f"{baseName:s}_{flagName:s}"
                flag = rename_signal(parentHwModule, flag, newName)
                self._dbgExplicitlyNamedSyncSignals.add(flag)

            return flag

    def _rtlChannelSyncFinalize(self, con: ConnectionsOfStage):
        """
        Before this function all concurrent IOs and their conditions are collected.
        In this function we resolve final enable conditions.
        """
        masters: List[HwIOOrValidReadyTuple] = []
        slaves: List[HwIOOrValidReadyTuple] = []
        extraConds: Dict[HwIOOrValidReadyTuple, RtlSignal] = {}
        skipWhens: Dict[HwIOOrValidReadyTuple, RtlSignal] = {}

        parentHwModule = self.netlist.parentHwModule
        seen: Set[InterfaceOrReadWriteNodeOrValidReadyTuple] = set()
        # :attention: It is important that outputs are iterated first, because if IO is
        # in inputs and outputs it needs to be slave and we are using first found and then
        # we are using seen set to filter already seen
        for masterOrSlaveList, ioList in ((slaves, con.outputs), (masters, con.inputs),):
            for ioRecord in ioList:
                ioRecord: IORecord
                node: Union[HlsNetNodeRead, HlsNetNodeWrite] = ioRecord.node
                hwIO: Optional[HwIO] = ioRecord.io
                flagsDictKey: InterfaceOrReadWriteNodeOrValidReadyTuple = ioRecord.ioUniqueKey
                if flagsDictKey in seen:
                    continue
                else:
                    seen.add(flagsDictKey)

                if not self._dbgAddSignalNamesToSync:
                    baseName = None
                elif hwIO is None or not isinstance(hwIO, (HwIOBase, RtlSignalBase)):
                    baseName = node.name
                else:
                    baseName = hwIO._name

                # resolve conditions for IO as input and output (some IO may be both)
                inputExtraCond = self._rtlChannelSyncFinalizeFlag(parentHwModule, con.inputs_extraCond, flagsDictKey, baseName, "extraCond", 1)
                inputSkipWhen = self._rtlChannelSyncFinalizeFlag(parentHwModule, con.inputs_skipWhen, flagsDictKey, baseName, "skipWhen", 0)
                oututExtraCond = self._rtlChannelSyncFinalizeFlag(parentHwModule, con.outputs_extraCond, flagsDictKey, baseName, "extraCond", 1)
                oututSkipWhen = self._rtlChannelSyncFinalizeFlag(parentHwModule, con.outputs_skipWhen, flagsDictKey, baseName, "skipWhen", 0)

                extraCond = RtlSignalBuilder.buildAndOptional(inputExtraCond, oututExtraCond)
                if extraCond is not None:
                    if isinstance(extraCond, HBitsConst):
                        assert int(extraCond) == 1, (node, "Must be 1 otherwise IO is never activated")
                        extraCond = None

                skipWhen = RtlSignalBuilder.buildAndOptional(inputSkipWhen, oututSkipWhen)
                if skipWhen is not None:
                    if isinstance(skipWhen, HBitsConst):
                        assert int(skipWhen) == 0, (node, "Must be 0 otherwise IO is never activated")
                        skipWhen = None

                valid, ready = ioRecord.validReady
                _valid, _ready = ioRecord.validReadyPresent
                isRead = isinstance(node, HlsNetNodeRead)
                hasValidDrivenFromLocalAck = node.hasValidOnlyToPassFlags() or (
                    not isRead and not isinstance(_valid, int) and isinstance(valid, int))
                hasReadyDrivenFromLocalAck = node.hasReadyOnlyToPassFlags() or (
                    isRead and not isinstance(_ready, int) and isinstance(ready, int))
                ack = NOT_SPECIFIED
                # exclude immediate edges because
                driveReadyFromLocalAck = True
                driveValidFromLocalAck = True
                # if (isinstance(node, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge))\
                #        and node.associatedWrite._getBufferCapacity() == 0) or \
                #    (isinstance(node, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge))\
                #        and node._getBufferCapacity() == 0):
                #    driveValidFromLocalAck &= node._rtlUseValid
                #    driveReadyFromLocalAck &= node._rtlUseReady

                driveValidFromLocalAck &= hasValidDrivenFromLocalAck and not isRead and not ioRecord.validHasCustomDriver
                driveReadyFromLocalAck &= hasReadyDrivenFromLocalAck and isRead and not ioRecord.readyHasCustomDriver

                if driveReadyFromLocalAck or driveValidFromLocalAck:
                    ack = RtlSignalBuilder.buildOrNegatedMaskOptional(extraCond, skipWhen)
                    if ack is None:
                        ack = 1
                    elif isinstance(ack, HBitsConst):
                        assert int(ack) == 1, node
                        ack = 1

                    if hasValidDrivenFromLocalAck:
                        if driveValidFromLocalAck:
                            assert isinstance(_valid, (RtlSignalBase, HwIOSignal)), (node, _valid)
                            con.stDependentDrives.append(_valid(ack))

                        if not isRead:
                            assert valid == 1, ("valid should not be used in sync tuple and should be present"
                                            " only in ioRecord.validReadyPresent", node, valid)
                    if hasReadyDrivenFromLocalAck:
                        if driveReadyFromLocalAck:
                            assert isinstance(_ready, (RtlSignalBase, HwIOSignal)), (node, _ready)
                            con.stDependentDrives.append(_ready(ack))
                        if isRead:
                            assert ready == 1, ("ready should not be used in sync tuple and should be present"
                                            " only in ioRecord.validReadyPresent", node, ready)
                # rm ready or valid which would be driven from this port because it has custom driver specified
                if isRead:
                    if ioRecord.readyHasCustomDriver:
                        ready = 1
                else:
                    if ioRecord.validHasCustomDriver:
                        valid = 1

                if valid == 1 and ready == 1:
                    # this IO has no read valid on its own but we may have to add virtual IO to implement stalling
                    # of this node if there is some extraCond or skipWhen condition
                    if ack is NOT_SPECIFIED:
                        ack = RtlSignalBuilder.buildOrOptional(extraCond, skipWhen)
                        if isinstance(ack, HBitsConst):
                            assert int(ack) == 1, node
                            ack = None
                    if isinstance(ack, int):
                        assert ack == 1, node
                        ack = None

                    if ack is not None:
                        # add virtual masters to implement stalling of this node for IO which
                        if baseName is not None:
                            ack = rename_signal(self.netlist.parentHwModule, ack, f"{baseName}_ack")
                            self._dbgExplicitlyNamedSyncSignals.add(ack)

                        virtualMaster = (ack, 1)
                        if virtualMaster not in seen:
                            masters.append(virtualMaster)
                            seen.add(virtualMaster)
                        if skipWhen is not None:
                            skipWhens[virtualMaster] = skipWhen

                        # :note: it is not required to set extraCond because it is part of ack
                else:
                    if skipWhen is not None:
                        skipWhens[(valid, ready)] = skipWhen

                    if extraCond is not None:
                        extraConds[(valid, ready)] = extraCond

                    masterOrSlaveList.append((valid, ready))

        if not skipWhens:
            skipWhens = None

        if not extraConds:
            extraConds = None

        return masters, slaves, extraConds, skipWhens

    def _rtlAllocateSyncStreamNode(self, con: ConnectionsOfStage) -> StreamNode:
        assert con.syncNode is None, "This method should be called only once per ConnectionsOfStage"
        if not con.inputs and not con.outputs:
            masters = []
            slaves = []
            extraConds = None
            skipWhen = None
            assert not con.inputs_extraCond, (self, con , con.inputs_extraCond)
            assert not con.outputs_extraCond, (self, con, con.outputs_extraCond)
            assert not con.inputs_skipWhen, (self, con  , con.inputs_skipWhen)
            assert not con.outputs_skipWhen, (self, con , con.outputs_skipWhen)

        else:
            masters, slaves, extraConds, skipWhen = self._rtlChannelSyncFinalize(con)

        sync = StreamNode(
            masters,
            slaves,
            extraConds=extraConds,
            skipWhen=skipWhen,
        )
        con.syncNode = sync
        return sync

    def _rtlAllocIoMux(self, ioMuxes: Dict[HwIO, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                             ioMuxesKeysOrdered: SetList[HwIO]):
        """
        After all read/write nodes constructed all RTL create a HDL switch to select RTL which should be active.
        """
        for io in ioMuxesKeysOrdered:
            muxCases = ioMuxes[io]
            if len(muxCases) == 1:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    caseList = muxCases[0][1]
                    assert isinstance(caseList, list), (caseList.__class__, caseList)
                    yield caseList
                else:
                    assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
                    # no MUX needed and we already merged the synchronization
            else:
                if isinstance(muxCases[0][0], HlsNetNodeWrite):
                    # create a write MUX
                    rtlMuxCases = []
                    for w, stms in muxCases:
                        caseCond = self._rtlAllocDatapathGetIoAck(w, self.name)
                        assert caseCond is not None, ("Because write object do not have any condition it is not possible to resolve which value should be MUXed to output interface", muxCases[0][0].dst)
                        rtlMuxCases.append((caseCond, stms))

                    stms = rtlMuxCases[0][1]
                    # create default case to prevent lath in HDL
                    if isinstance(stms, HdlAssignmentContainer):
                        defaultCase = [stms.dst(None), ]
                    else:
                        defaultCase = [asig.dst(None) for asig in stms]
                    yield SwitchLogic(rtlMuxCases, default=defaultCase)
                else:
                    assert isinstance(muxCases[0][0], HlsNetNodeRead), muxCases
                    # no MUX needed and we already merged the synchronization

    def rtlAllocDatapath(self):
        """
        Allocate main RTL object which are required from HlsNetNode instances assigned to this element.
        """
        raise NotImplementedError("Implement in child class")

    def rtlAllocSync(self):
        """
        Instantiate an additional RTL objects to implement the synchronization of the element
        which are not directly present in input HlsNetNode instances.
        """
        raise NotImplementedError("Implement in child class")

    def _getBaseName(self) -> str:
        namePrefixLen = len(self.netlist.namePrefix)
        return self.name[namePrefixLen:]

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d} {self.name:s}>"


ArchElmEdge = Tuple[ArchElement, ArchElement]
