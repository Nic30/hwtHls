from typing import Union, List, Dict, Tuple, Optional, Generator, Literal, Set

from hwt.constants import NOT_SPECIFIED
from hwt.hdl.const import HConst
from hwt.hdl.operatorDefs import HOperatorDef
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.defs import BIT
from hwt.hdl.types.hdlType import HdlType
from hwt.hwIO import HwIO
from hwt.mainBases import RtlSignalBase
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage, \
    ConnectionsOfStageList
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, \
    TimeIndependentRtlResourceItem, INVARIANT_TIME
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeFsmStateEn, \
    HlsNetNodeStageAck
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeIn
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk, indexOfClkPeriod
from hwtHls.platform.opRealizationMeta import EMPTY_OP_REALIZATION
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite


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

    def __init__(self, netlist: "HlsNetlistCtx", name:str, namePrefix:str,
                 subNodes: SetList[HlsNetNode],
                 connections: ConnectionsOfStageList):
        HlsNetNodeAggregate.__init__(self, netlist, subNodes, name)
        self.namePrefix = namePrefix
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
             nextSig:Optional[RtlSignalBase]=NOT_SPECIFIED) -> RtlSignal:
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
            self._addNodeIntoScheduled(clkIndex, internI.obj, allowNewClockWindow=True)
        return outerO, internI

    @override
    def _addInput(self, t:HdlType, name:Optional[str], time:Optional[SchedTime]=None) -> Tuple[HlsNetNodeIn, HlsNetNodeOut]:
        outerI, internO = super(ArchElement, self)._addInput(t, name, time=time)
        if time is not None:
            clkIndex = indexOfClkPeriod(time, self.netlist.normalizedClkPeriod)
            self._addNodeIntoScheduled(clkIndex, internO.obj, allowNewClockWindow=True)
        return outerI, internO

    @override
    def filterNodesUsingSet(self, removed: Set[HlsNetNode], recursive=False, clearRemoved=True):
        if self.scheduledZero is not None:
            for _, state in self.iterStages():
                state[:] = (n for n in state if n not in removed)
        super(ArchElement, self).filterNodesUsingSet(removed, recursive=recursive, clearRemoved=clearRemoved)

    def filterNodesUsingSetInSingleStage(self, removed: Set[HlsNetNode], stageIndex: int, recursive=False, clearRemoved=True):
        stage = self.getStageForClock(stageIndex)
        stage[:] = (n for n in stage if n not in removed)
        super(ArchElement, self).filterNodesUsingSet(removed, recursive=recursive, clearRemoved=clearRemoved)

    def filterNodesUsingRemovedSetInSingleStage(self, stageIndex: int, recursive=False):
        stage = self.getStageForClock(stageIndex)
        removed = self.getHlsNetlistBuilder()._removedNodes
        stage[:] = (n for n in stage if n not in removed)
        super(ArchElement, self).filterNodesUsingRemovedSet(recursive=recursive)

    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        """
        Iterate slots for clock windows which are containing scheduled nodes in this element.
        """
        raise NotImplementedError("Implement this method in child class", self)

    def getStageForTime(self, time: SchedTime) -> List[HlsNetNode]:
        assert time >= 0, time
        return self.getStageForClock(time // self.netlist.normalizedClkPeriod)

    def getStageForClock(self, clkIndex: int, createIfNotExists=False) -> List[HlsNetNode]:
        """
        Get clock window slot for a specified clock index.
        :param createIfNotExists: generate a new clock window container if it is 
            missing in this element
        """
        raise NotImplementedError("Implement this method in child class", self)

    def getStageEnable(self, clkIndex: int) -> Tuple[Optional[HlsNetNodeOut], bool]:
        """
        Get existing or create a :class:`HlsNetNodeFsmStateEn` (is 1 if stage is allowed to perform its function)
        
        :return: tuple optional out of HlsNetNodeFsmStateEn for specified and flag which is True if HlsNetNodeFsmStateEn was just allocated
        """
        netlist = self.netlist
        con = self.connections[clkIndex]
        if con.fsmStateEnNode:
            return con.fsmStateEnNode._outputs[0], False

        enNode = HlsNetNodeFsmStateEn(netlist)
        enNode.resolveRealization()
        enNode._setScheduleZeroTimeSingleClock(clkIndex * netlist.normalizedClkPeriod)
        self._addNodeIntoScheduled(clkIndex, enNode)
        return enNode._outputs[0], True

    def getStageAckNode(self, clkIndex: int) -> Tuple[HlsNetNodeStageAck, bool]:
        """
        Get existing or create a :class:`HlsNetNodeStageAck` (a sink for ack signal which is 1 if stage performing its function)
        """
        con: ConnectionsOfStage = self.connections.getForClkIndex(clkIndex)
        if con.fsmStateAckNode is not None:
            return con.fsmStateAckNode, False
        stAck = HlsNetNodeStageAck(self.netlist)
        stAck.resolveRealization()
        stAck._setScheduleZeroTimeSingleClock((clkIndex + 1) * self.netlist.normalizedClkPeriod - 1)
        self._addNodeIntoScheduled(clkIndex, stAck)
        return stAck, True

    def _addNodeIntoScheduled(self, clkI: int, node: HlsNetNode, allowNewClockWindow=False):
        """
        :attention: It is expected that the node itself is already scheduled
        """
        if node.parent is None:
            node.parent = self
        else:
            assert node.parent is self, ("Node can have only one parent", node, node.parent, self)
        if self._beginClkI is None or clkI < self._beginClkI:
            self._beginClkI = clkI
        if clkI >= len(self.connections):
            assert allowNewClockWindow, (self, clkI, node)
            for _ in range(len(self.connections), clkI):
                self.connections.append(None)
            self.connections.append(ConnectionsOfStage(self, len(self.connections)))

        con = self.connections[clkI]
        if con is None:
            assert allowNewClockWindow, (self, clkI, node)
            con = self.connections[clkI] = ConnectionsOfStage(self, clkI)

        con: ConnectionsOfStage
        beginClkI = self._beginClkI
        if beginClkI is None or beginClkI > clkI:
            self._beginClkI = clkI
        endClkI = self._endClkI
        if endClkI is None or endClkI < clkI:
            self._endClkI = clkI

        self.getStageForClock(clkI, createIfNotExists=allowNewClockWindow).append(node)
        self.subNodes.append(node)
        if isinstance(node, HlsNetNodeFsmStateEn):
            assert con.fsmStateEnNode is None, ("only one per clk window", self, con, node)
            con.fsmStateEnNode = node
        elif isinstance(node, HlsNetNodeStageAck):
            assert con.fsmStateAckNode is None, ("only one per clk window", self, con, node)
            con.fsmStateAckNode = node
        elif isinstance(node, HlsNetNodeFsmStateWrite):
            assert con.fsmStateWriteNode is None, ("only one per clk window", self, con, node)
            con.fsmStateWriteNode = node

    @override
    def resolveRealization(self):
        self.assignRealization(EMPTY_OP_REALIZATION)  # ports do not have any extra delay

    def addImplicitSyncChannelsInsideOfElm(self) -> bool:
        """
        Create HlsNetNodeReadForwardedge/HlsNetNodeWriteForwardedge pairs to implement synchronization
        between parts of this element.
        
        :returns: True if netlist was changed
        """
        return False

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
        assert data is not None
        assert outOrTime is not None
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
                assert curTir.isForwardDeclr, ("Only forward declarations may be redefined", curTir, outOrTime, data)
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

    def rtlAllocHlsNetNodeOut(self, o: HlsNetNodeOut) -> Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        """
        Allocate all RTL which is represented by provided output
        """
        assert isinstance(o, HlsNetNodeOut), o
        _o = self.netNodeToRtl.get(o, None)

        if _o is None:
            if HdlType_isVoid(o._dtype):
                return []
            oObj: HlsNetNode = o.obj
            assert not oObj._isRtlAllocated, (
                "Node was allocated, but the output rtl is missing, this could be the case only for outputs of void type, "
                "This error could be also a sign of node being allocated/used directly in other element (without port on this element)", o)

            assert oObj.scheduledOut is not None, ("Node must be scheduled", oObj)
            clkI = start_clk(oObj.scheduledOut[o.out_i], self.netlist.normalizedClkPeriod)
            if len(self.connections) <= clkI or self.connections[clkI] is None:
                raise AssertionError("Asking for node output which should have forward declaration but it is missing", self, o, clkI)
            # new allocation, use registered automatically
            assert not oObj._isRtlAllocated, (o, "if rtl is allocated the output should already had the rlt in netNodeToRtl")
            _o = oObj.rtlAlloc(self)
            assert oObj._isRtlAllocated, o
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
                    raise AssertionError(self, "Node did not instantiate its output", oObj, o)
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
        :meth:`~.rtlAllocHlsNetNodeOut` method with also gets the RTL resource in specified time.
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

    def rtlAllocHlsNetNodeInInTime(self, i: HlsNetNodeIn, time:int,
                                      ) -> TimeIndependentRtlResourceItem:
        return self.rtlAllocHlsNetNodeOutInTime(i.obj.dependsOn[i.in_i], time)

    def rtlAllocHlsNetNodeInDriverIfAlocatedElseForwardDeclr(self, i: HlsNetNodeIn)\
            ->Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        obj = i.obj
        dep = obj.dependsOn[i.in_i]
        assert isinstance(dep, HlsNetNodeOut), dep
        _o = self.netNodeToRtl.get(dep, None)
        if _o is None:
            defT = dep.obj.scheduledOut[dep.out_i]
            useT = obj.scheduledIn[i.in_i]
            return self.rtlAllocOutDeclr(self, dep, defT).get(useT)

        return self.rtlAllocHlsNetNodeOutInTime(dep, obj.scheduledIn[i.in_i])

    def rtlAllocHlsNetNodeInDriverIfExists(self, i: Optional[HlsNetNodeIn])\
            ->Union[TimeIndependentRtlResourceItem, List[HdlStatement]]:
        if i is None:
            return None
        obj = i.obj
        dep = obj.dependsOn[i.in_i]
        assert dep
        return self.rtlAllocHlsNetNodeOutInTime(dep, obj.scheduledIn[i.in_i])

    # def rtlAllocDatapathRead(self, node: HlsNetNodeRead, con: ConnectionsOfStage, rtl: List[HdlStatement],
    #                         validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
    #    """
    #    :attention: :see: :meth:`~._rtlAllocDatapathIo`
    #    """
    #    self._rtlAllocDatapathIo(node.src, node, con, rtl, True, validHasCustomDriver, readyHasCustomDriver)
    #
    # def rtlAllocDatapathWrite(self, node: HlsNetNodeWrite, con: ConnectionsOfStage, rtl: List[HdlStatement],
    #                          validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
    #    """
    #    :attention: :see: :meth:`~._rtlAllocDatapathIo`
    #    """
    #    self._rtlAllocDatapathIo(node.dst, node, con, rtl, False, validHasCustomDriver, readyHasCustomDriver)
    def rtlAllocDatapathRead(self, node: HlsNetNodeRead, rtlReadySignal: Optional[RtlSignal], con: ConnectionsOfStage, rtl: List[HdlStatement]):
        self._rtlAllocDatapathIo(node.src, node, rtlReadySignal, con, rtl)

    def rtlAllocDatapathWrite(self, node: HlsNetNodeWrite, rtlValidSignal: Optional[RtlSignal], con: ConnectionsOfStage, rtl: List[HdlStatement]):
        self._rtlAllocDatapathIo(node.dst, node, rtlValidSignal, con, rtl)

    def _rtlAllocDatapathIo(self,
                    hwIO: Optional[HwIO],
                    node: Union[HlsNetNodeRead, HlsNetNodeWrite],
                    rtlIoEnableSignal: Optional[RtlSignal],
                    con: ConnectionsOfStage,
                    rtl: List[HdlStatement]):
        """
        There may be multiple read/write instances accessing the same hw interface in this ConnectionsOfStage.
        If this is the case it is proven that the access is concurrent.
        Because of this we first have to see all nodes in stage before resolving enable conditions and multiplexing for hw interface.
        """
        assert isinstance(rtl, list), (node, rtl.__class__, rtl)
        ec = self.rtlAllocHlsNetNodeInDriverIfExists(node.extraCond)
        if ec is not None:
            ec = ec.data

        if hwIO is None:
            hwIO = node

        muxVariants = con.fsmIoMuxCases.get(hwIO, None)
        if muxVariants is None:
            muxVariants = con.fsmIoMuxCases[hwIO] = []
        else:
            assert hwIO is not None, ("Nodes without hwIO can not be duplicated", node)
        muxVariants.append((node, ec, rtlIoEnableSignal, rtl))

    # def _rtlAllocDatapathIo(self,
    #                hwIO: Optional[HwIO],
    #                node: Union[HlsNetNodeRead, HlsNetNodeWrite],
    #                con: ConnectionsOfStage,
    #                rtl: List[HdlStatement],
    #                isRead: bool,
    #                validHasCustomDriver:bool,
    #                readyHasCustomDriver:bool):
    #    """
    #    There may be multiple read/write instances accessing the same hw interface in this ConnectionsOfStage.
    #    If this is the case it is proven that the access is concurrent.
    #    Because of this we first have to see all nodes in stage before resolving enable conditions for hw interface.
    #
    #    :attention: validHasCustomDriver are related to IO and must be set always the same when calling this method multiple times for this IO
    #    """
    #    assert isinstance(rtl, list), (node, rtl.__class__, rtl)
    #    if hwIO is None:
    #        assert not node._rtlUseValid and not node._rtlUseReady, node
    #        valid = 1
    #        ready = 1
    #        validReadyPhysicallyPresent = (1, 1)
    #        if isRead:
    #            assert HdlType_isVoid(node._portDataOut._dtype), (
    #                "Node without any HwIO or sync must not have any data", node)
    #            # if isinstance(node, (HlsNetNodeReadBackedge, HlsNetNodeReadForwardedge)):
    #            #    hwIO = node.associatedWrite
    #        else:
    #            assert HdlType_isVoid(node.dependsOn[node._portSrc.in_i]._dtype), (
    #                "Node without any HwIO or sync must not have any data", node)
    #        # we need some object to store extraCond and skipWhen
    #    else:
    #        assert isinstance(hwIO, (HwIO, RtlSignalBase)), ("Node should already have interface resolved", node, hwIO)
    #        validReadyPhysicallyPresent = HwIO_getSyncTuple(hwIO)
    #        valid, ready = validReadyPhysicallyPresent
    #
    #        # if isinstance(node, HlsNetNodeWrite) and node._isFlushable:
    #        #    ready, valid = node.getRtlFlushReadyValidSignal()
    #        #    if ready is None:
    #        #        ready = 1
    #
    #        # rm ready/valid from sync as it will be driven only form node flags instead from StreamNode
    #        if isRead:
    #            if not node._isBlocking:
    #                valid = 1  # rm valid from sync because we do not have to wait for it
    #            if not node._rtlUseReady:
    #                ready = 1
    #            if isinstance(node, HlsNetNodeReadForwardedge):
    #                if not node._rtlUseValid:
    #                    valid = 1
    #        else:
    #            if not node._isBlocking:
    #                ready = 1  # rm ready from sync because we do not have to wait for it
    #            if not node._rtlUseValid:  #  and not node._isFlushable
    #                valid = 1
    #            if isinstance(node, HlsNetNodeWriteForwardedge):
    #                if not node._rtlUseReady:
    #                    ready = 1
    #
    #    if isRead:
    #        ioContainer = con.inputs
    #    else:
    #        ioContainer = con.outputs
    #
    #    validReadyForSync = (valid, ready)
    #
    #    if valid == 1 and ready == 1:
    #        if hwIO is None:
    #            keyForFlagDicts = node
    #        else:
    #            keyForFlagDicts = hwIO
    #    else:
    #        keyForFlagDicts = validReadyForSync
    #
    #    assert keyForFlagDicts is not None and\
    #           not (isinstance(keyForFlagDicts , tuple) and\
    #                keyForFlagDicts == (1, 1)), node
    #
    #    io = IORecord(node, hwIO, validReadyForSync,
    #                  keyForFlagDicts, validReadyPhysicallyPresent,
    #                  validHasCustomDriver, readyHasCustomDriver)
    #    ioContainer.append(io)
    #
    #    if hwIO is None:
    #        assert not rtl, ("If it has no HW interface (it is only virtual read/write)"
    #                         " it should not produce any rtl", node)
    #    else:
    #        muxVariants = con.ioMuxes.get(hwIO, None)
    #        if muxVariants is None:
    #            muxVariants = con.ioMuxes[hwIO] = []
    #        muxVariants.append((node, rtl))
    #
    #    if isRead:
    #        assert keyForFlagDicts not in con.outputs_extraCond, (node, keyForFlagDicts)
    #        io_extraCond = con.inputs_extraCond
    #    else:
    #        assert keyForFlagDicts not in con.inputs_extraCond, (node, keyForFlagDicts)
    #        io_extraCond = con.outputs_extraCond
    #
    #    self._rtlAllocDatapathAddIoToConnections(node, isRead, keyForFlagDicts,
    #                                             io_extraCond)
    #
    # def _rtlAllocDatapathAddIoToConnections(self,
    #               node: Union[HlsNetNodeRead, HlsNetNodeWrite],
    #               isRead: bool,
    #               keyForFlagDicts: InterfaceOrReadWriteNodeOrValidReadyTuple,
    #               io_extraCond: Dict[InterfaceOrReadWriteNodeOrValidReadyTuple, OrMemberList],
    #               ):
    #    """
    #    Add IO extraCond to io_extraConds dictionary
    #
    #    :attention: This function is run for a single read/write node but there may be multiple such nodes
    #        in a single clock period slot. Such a IO may be concurrent and thus skipWhen and extraCond must be merged.
    #    """
    #    ec = self.rtlAllocHlsNetNodeInDriverIfExists(node.extraCond)
    #    if ec is not None:
    #        ec = ec.data
    #        curFlag = io_extraCond.get(keyForFlagDicts, None)
    #        if curFlag is not None:
    #            curFlag.data.append(ec)
    #        else:
    #            curFlag = OrMemberList([ec, ])
    #            io_extraCond[keyForFlagDicts] = curFlag
    #
    #    assert node.skipWhen is None, ("This port should be already lowered by RtlArchPassSyncLower", node)
    #    if not isRead:
    #        assert node._forceEnPort is None, ("This port should be already lowered by RtlArchPassSyncLower", node)
    #        # assert node._mayFlushPort is None, ("This port should be already lowered by RtlArchPassSyncLower", node)
    #
    # def _rtlAllocDatapathGetIoAck(self, node: Union[HlsNetNodeRead, HlsNetNodeWrite], namePrefix:str) -> Optional[RtlSignal]:
    #    """
    #    Use extraCond, skipWhen condition to get enable condition.
    #    """
    #    ack = None
    #    extraCond = self.rtlAllocHlsNetNodeInDriverIfExists(node.extraCond)
    #    if extraCond is not None:
    #        ack = extraCond.data
    #
    #    assert node.skipWhen is None, ("skipWhen should be already lowered", node,)
    #
    #    if isinstance(ack, HBitsConst):
    #        assert int(ack) == 1, (node, "If ack=0 this means that channel is always stalling")
    #        ack = None
    #
    #    if ack is not None and self._dbgAddSignalNamesToSync:
    #        ack = rename_signal(self.netlist.parentHwModule, ack, f"{namePrefix:s}n{node._id}_ack")
    #
    #    return ack

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
