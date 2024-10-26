from typing import List, Set, Tuple, Union, Generator, Optional

from hwt.code import Switch, If
from hwt.hdl.const import HConst
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hwIO import HwIO
from hwt.math import log2ceil
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.architecture.connectionsOfStage import \
    setNopValIfNotSet, ConnectionsOfStage, ConnectionsOfStageList
from hwtHls.architecture.syncUtils import HwIO_getSyncSignals
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, INVARIANT_TIME, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import  HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtLib.logic.rtlSignalBuilder import RtlSignalBuilder
from ipCorePackager.constants import INTF_DIRECTION


class ArchElementFsm(ArchElement):
    """
    An HlsNetNode which represents FSM. FSM is composed of group of nodes.

    .. figure:: ./_static/ArchElementFsm.png

    :see: `~.ArchElement`

    #:ivar fsm: an original FsmMeta object from which this was created
    """

    def __init__(self, netlist: HlsNetlistCtx, name: str, namePrefix:str,
                 subNodes: Optional[SetList[HlsNetNode]]=None,
                 stages: List[List[HlsNetNode]]=None):
        beginClkI = None
        endClkI = None
        if subNodes is None:
            subNodes = SetList()
        if stages is None:
            self.stages = []
            stageCons = ConnectionsOfStageList(netlist.normalizedClkPeriod, ())
        else:
            self.stages = stages
            stageCons = ConnectionsOfStageList(netlist.normalizedClkPeriod,
                                               (ConnectionsOfStage(self, clkI)
                                                for clkI, _ in enumerate(self.stages)))
        # if fsm is None:
        #    stateCons = ConnectionsOfStageList(netlist.normalizedClkPeriod, ())
        # else:
        #    assert fsm.states, fsm
        #    for clkI, st in enumerate(fsm.states):
        #        if st:
        #            if beginClkI is None:
        #                beginClkI = clkI
        #            endClkI = clkI
        #
        #    stateCons = ConnectionsOfStageList(clkPeriod, (ConnectionsOfStage(self, i)
        #                                                    if st else None for i, st in enumerate(fsm.states)))
        ArchElement.__init__(self, netlist, name, namePrefix, subNodes, stageCons)
        self._beginClkI = beginClkI
        self._endClkI = endClkI
        self._rtlStateReg: Optional[RtlSignal] = None

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        return ArchElementPipeline.clone(memo, keepTopPortsConnected)
        # y, isNew = ArchElement.clone(self, memo, keepTopPortsConnected)
        # if isNew:
        #    y.fsm = self.fsm.clone(memo)[0]
        #    y.stateEncoding = copy(self.stateEncoding)
        # return y, isNew

    @override
    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        return ArchElementPipeline.iterStages(self)
        # fsm = self.fsm
        # if fsm is None:
        #    return
        # for clkI, nodes in enumerate(fsm.states):
        #    if nodes:
        #        yield (clkI, nodes)

    def hasUsedStateForClkI(self, clkI: int) -> bool:
        return clkI < len(self.stages) and self.stages[clkI]

    @override
    def getStageForClock(self, clkIndex: int, createIfNotExists=False) -> List[HlsNetNode]:
        return ArchElementPipeline.getStageForClock(self, clkIndex, createIfNotExists)
        # if createIfNotExists:
        #    return self.fsm.addState(clkIndex)
        # else:
        #    return self.fsm.states[clkIndex]

    def _iterTirsOfNode(self, n: HlsNetNode) -> Generator[TimeIndependentRtlResource, None, None]:
        for o in n._outputs:
            if o in self.netNodeToRtl and not HdlType_isNonData(o._dtype):
                tirs = self.netNodeToRtl[o]
                if isinstance(tirs, TimeIndependentRtlResource):
                    yield tirs
                else:
                    yield from tirs

    @override
    def rtlRegisterOutputRtlSignal(self, outOrTime: Union[HlsNetNodeOut, SchedTime],
                                data: Union[RtlSignal, HwIO, HConst],
                                isExplicitRegister: bool,
                                isForwardDeclr: bool,
                                mayChangeOutOfCfg: bool):
        tir = super(ArchElementFsm, self).rtlRegisterOutputRtlSignal(
            outOrTime, data, isExplicitRegister, isForwardDeclr, mayChangeOutOfCfg)
        # mark value in register as persistent until the end of FSM
        if isinstance(outOrTime, HlsNetNodeOut) and isinstance(outOrTime.obj, HlsProgramStarter):
            # because we want to consume token from the starter only on transition in this FSM
            con: ConnectionsOfStage = self.connections[0]
            con.stateChangeDependentDrives.append(tir.valuesInTime[0].data.next.drivers[0])

        if tir.timeOffset == INVARIANT_TIME:
            # this is stable value and does not need any register storage
            return

        clkPeriod = self.netlist.normalizedClkPeriod
        _endClkI = self._endClkI

        assert len(tir.valuesInTime) == 1, ("Value must not be used yet because we need to set persistence ranges first.", tir)

        if not tir.persistenceRanges:
            # if value persistenceRanges were not discovered yet
            peristentFromThisClk = False
            if isinstance(outOrTime, HlsNetNodeOut):
                node = outOrTime.obj
                if isinstance(node, HlsNetNodeRead) and node._isBlocking:
                    w = node.associatedWrite
                    if w is not None and w.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                        wClkI = w.scheduledZero // clkPeriod
                        for u in node.usedBy[outOrTime.out_i]:
                            if u.obj.scheduledOut[u.in_i] // clkPeriod > wClkI:
                                raise NotImplementedError("Use after write, need to create reg for copy of current val")
                        peristentFromThisClk = True
                        
                elif isinstance(node, HlsNetNodeWrite) and node.allocationType == CHANNEL_ALLOCATION_TYPE.REG:
                    r = node.associatedRead
                    if r is not None and r.parent is self:
                        peristentFromThisClk = True

            # value for the first clock behind this clock period and the rest is persistent in this register
            persistentFromClkI = start_clk(tir.timeOffset, clkPeriod)
            if not peristentFromThisClk:
                persistentFromClkI += 1
            if persistentFromClkI <= _endClkI:
                tir.markPersistent(persistentFromClkI, _endClkI)

            self.connections.getForTime(tir.timeOffset).signals.append(tir.valuesInTime[0])

        return tir

    def _initNopValsOfIoForHwIO(self, hwIO: Union[HwIO], dir_: INTF_DIRECTION):
        if dir_ == INTF_DIRECTION.MASTER:
            # to prevent latching when interface is not used
            syncSignals = HwIO_getSyncSignals(hwIO)
            setNopValIfNotSet(hwIO, None, syncSignals)
        else:
            assert dir_ == INTF_DIRECTION.SLAVE, (hwIO, dir_)
            syncSignals = HwIO_getSyncSignals(hwIO)

        for s in syncSignals:
            setNopValIfNotSet(s, 0, ())

    def _initNopValsOfIo(self):
        """
        initialize nop value which will drive the IO when not used
        """
        for nodes in self.stages:
            for node in nodes:
                if isinstance(node, HlsNetNodeWrite):
                    if node.dst is not None:
                        self._initNopValsOfIoForHwIO(node.dst, INTF_DIRECTION.MASTER)

                elif isinstance(node, HlsNetNodeRead):
                    if node.src is not None:
                        self._initNopValsOfIoForHwIO(node.src, INTF_DIRECTION.SLAVE)

    @override
    def rtlStatesMayHappenConcurrently(self, stateClkI0: int, stateClkI1: int):
        return stateClkI0 == stateClkI1

    #@override
    #def rtlAllocDatapathRead(self, node: HlsNetNodeRead, con: ConnectionsOfStage, rtl: List[HdlStatement],
    #                          validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
    #    if isinstance(node, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge)) and \
    #            node.associatedWrite is not None and \
    #            node.associatedWrite.allocationType != CHANNEL_ALLOCATION_TYPE.BUFFER:
    #        # nodes of this type are just registers and do not have any IO
    #        return
    #    self._rtlAllocDatapathIo(node.src, node, con, rtl, True, validHasCustomDriver, readyHasCustomDriver)
    #
    #@override
    #def rtlAllocDatapathWrite(self, node: HlsNetNodeWrite, con: ConnectionsOfStage, rtl: List[HdlStatement],
    #                          validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
    #    if isinstance(node, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)) and\
    #            node.allocationType != CHANNEL_ALLOCATION_TYPE.BUFFER:
    #        con.stateChangeDependentDrives.extend(rtl)
    #        # nodes of this type are just registers and do not have any IO
    #        return
    #    self._rtlAllocDatapathIo(node.dst, node, con, rtl, False, validHasCustomDriver, readyHasCustomDriver)

    def _rtlAllocDeclareStateReg(self):
        stateEncodingA: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = self.netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        assert stateEncodingA is not None, ("HlsAndRtlNetlistAnalysisPassFsmStateEncoding should be already prepared before calling rtlAlloc")
        stateEncoding = stateEncodingA.stateEncoding[self]

        stateCnt = sum(1 if st else 0 for st in self.iterStages())
        if stateCnt > 1:
            # if there is more than 1 state
            stReg = self._reg(f"n{self._id:d}_fsmSt",
                           HBits(log2ceil(max(stateEncoding.values()) + 1)),
                           def_val=0)
        else:
            # because there is just a single state, the state value has no meaning
            stReg = None
        self._rtlStateReg = stReg

    @override
    def rtlAllocDatapath(self):
        """
        Instantiate logic in the states

        :note: This function does not perform efficient register allocations.
            Instead each value is store in individual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
        """
        # assert self.fsm.transitionTable, ("Transition table should be already generated by HlsAndRtlNetlistPassFsmDetectTransitionTable", self)
        self._rtlAllocDeclareStateReg()
        for (nodes, con) in zip(self.stages, self.connections):
            con: ConnectionsOfStage
            for node in nodes:
                node: HlsNetNode
                if node._isRtlAllocated:
                    continue
                assert node.scheduledIn is not None, ("Node must be scheduled", node)
                assert node.dependsOn is not None, ("Node must not be destroyed", node)
                node.rtlAlloc(self)

        for con in self.connections:
            con: ConnectionsOfStage
            if con is None:
                continue
            for rtl in con.rtlAllocIoMux():
                con.stateDependentDrives.extend(rtl)

    @override
    def rtlAllocSync(self):
        stateEncodingA: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = self.netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        assert stateEncodingA is not None, ("HlsAndRtlNetlistAnalysisPassFsmStateEncoding should be already prepared before calling rtlAlloc")
        stateEncoding = stateEncodingA.stateEncoding[self]

        self._initNopValsOfIo()
        # instantiate control of the FSM

        # used to prevent duplication of registers which are just latching the value
        # without modification through multiple stages
        seenRegs: Set[TimeIndependentRtlResourceItem] = set()
        stReg = self._rtlStateReg
        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        usedClks = iter([clkI for clkI in stateEncodingA.usedStates[self]])
        next(usedClks, None)  # skip first
        for clkI, con in enumerate(self.connections):
            if not self.hasUsedStateForClkI(clkI):
                assert con is None, (self, clkI)
                continue

            nextClkI = next(usedClks, None)
            con: ConnectionsOfStage
            assert con is not None, ("If state is used there must be ConnectionsOfStage object for this clock window", self, clkI)
            if nextClkI is not None:
                for curV in con.signals:
                    curV: TimeIndependentRtlResourceItem
                    # if the value has a register at the end of this stage
                    nextStVal = curV.parent.checkIfExistsInClockCycle(nextClkI)
                    if nextStVal is not None and nextStVal.isRltRegister() and not nextStVal in seenRegs:
                        con.stateChangeDependentDrives.append(nextStVal.data.next.drivers[0])
                        seenRegs.add(nextStVal)

            # unconditionalTransSeen = False
            # inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            #con.rtlChannelSyncFinalize(self.netlist.parentHwModule,
            #                           self._dbgAddSignalNamesToSync, self._dbgExplicitlyNamedSyncSignals)

            # prettify stateAck signal name if required
            stateAck = con.stageAck

            # reduce if ack is a constant value
            if isinstance(stateAck, (bool, int, HConst)):
                assert bool(stateAck) == 1, ("If synchronization of state is always stalling it should be already optimized out", self, clkI)
                stateAck = None
            else:
                assert stateAck._dtype.bit_length() == 1, (stateAck, self, clkI)

            stI = stateEncoding[clkI]
            _stateAck = stateAck
            # and ack with state en, to assert that
            if stReg is not None:
                stEn = stReg._eq(stI)
                stateAck = RtlSignalBuilder.buildAndOptional(stateAck, stEn)
                if con.stageEnable is not None:
                    con.stageEnable(stEn)
            elif con.stageEnable is not None:
                con.stageEnable(1)

            assert con.fsmStateWriteNode is not None, ("Should be constructed by syncLowering", self, clkI)
            # build next state logic from transitionTable
            # :note: isinstance(x[1], int) to have unconditional transitions as last
            # for dstStI, c in sorted(self.fsm.transitionTable[clkI].items(), key=lambda tr: (isinstance(tr[1], (int, HBitsConst)), tr[0])):
            #    assert not unconditionalTransSeen, "If there is an unconditional transition from this state it must be the last one"
            #    if c == 1:
            #        unconditionalTransSeen = True
            #        c = stateAck
            #
            #    elif isinstance(c, (bool, int)):
            #        assert c == 0, c
            #        continue
            #    else:
            #        assert c._dtype.bit_length() == 1, c
            #        c = RtlSignalBuilder.buildAndOptional(c, stateAck)
            #
            #    if stReg is not None:
            #        if c is None:
            #            c = True
            #        inStateTrans.append((c, stReg(self.stateEncoding[dstStI])))

            stateChangeDependentDrives = con.stateChangeDependentDrives

            if stateAck is not None:
                # if stateAck is not always satisfied create parent if to load registers conditionally
                stateChangeDependentDrives = If(_stateAck, stateChangeDependentDrives)

            stateTrans.append((stI, [  # SwitchLogic(inStateTrans),
                                     *con.stateDependentDrives,
                                     stateChangeDependentDrives,
                                     #con.rtlAllocSync()
                                     ]))

        self._rtlSyncAllocated = True

        if stReg is None:
            # do not create a state switch statement is there is no state register (and FSM has just 1 state)
            assert len(stateTrans) == 1
            return stateTrans[0][1]
        else:
            return Switch(stReg).add_cases(stateTrans)
