from typing import List, Set, Tuple, Union, Dict, Generator

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.code import SwitchLogic, Switch, If
from hwt.code_utils import rename_signal
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import HBits
from hwt.hdl.types.bitsConst import HBitsConst
from hwt.hdl.const import HConst
from hwt.math import log2ceil
from hwt.pyUtils.setList import SetList
from hwt.hwIO import HwIO
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.connectionsOfStage import \
    setNopValIfNotSet, ConnectionsOfStage, ConnectionsOfStageList
from hwtHls.architecture.syncUtils import HwIO_getSyncSignals
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, INVARIANT_TIME, \
    TimeIndependentRtlResourceItem
from hwtHls.netlist.analysis.detectFsms import IoFsm
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isNonData
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeReadForwardedge, \
    HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import  HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk, indexOfClkPeriod
from hwtHls.typingFuture import override
from hwtLib.logic.rtlSignalBuilder import RtlSignalBuilder
from ipCorePackager.constants import INTF_DIRECTION
from copy import copy


class ArchElementFsm(ArchElement):
    """
    An HlsNetNode which represents FSM. FSM is composed of group of nodes.

    .. figure:: ./_static/ArchElementFsm.png

    :see: `~.ArchElement`

    :ivar fsm: an original IoFsm object from which this was created
    :ivar transitionTable: a dictionary source stateI to dictionary destination stateI to condition for transition
    :ivar stateEncoding: a dictionary mapping state index to a value which will be used in RTL to represent this state.
    """

    def __init__(self, netlist: HlsNetlistCtx, name: str, subNodes: SetList[HlsNetNode], fsm: IoFsm):
        self.fsm = fsm
        clkPeriod = self.normalizedClkPeriod = netlist.normalizedClkPeriod
        assert fsm.states, fsm

        beginClkI = None
        endClkI = None
        for clkI, st in enumerate(fsm.states):
            if st:
                if beginClkI is None:
                    beginClkI = clkI
                endClkI = clkI

        stateCons = ConnectionsOfStageList(clkPeriod, (ConnectionsOfStage(self, i) if st else None for i, st in enumerate(fsm.states)))
        ArchElement.__init__(self, netlist, name, subNodes, stateCons)
        self._beginClkI = beginClkI
        self._endClkI = endClkI
        self.transitionTable: Dict[int, Dict[int, Union[bool, RtlSignal]]] = {}
        self.stateEncoding: Dict[int, int] = {}

    @override
    def clone(self, memo:dict, keepTopPortsConnected:bool) -> Tuple["HlsNetNode", bool]:
        y, isNew = ArchElement.clone(self, memo, keepTopPortsConnected)
        if isNew:
            y.fsm = self.fsm.clone(memo)[0]
            y.transitionTable = copy(self.transitionTable)
            y.stateEncoding = copy(self.stateEncoding)
        return y, isNew

    @override
    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        fsm = self.fsm
        for clkI, nodes in enumerate(fsm.states):
            if nodes:
                yield (clkI, nodes)

    @override
    def getStageForClock(self, clkIndex: int) -> List[HlsNetNode]:
        return self.fsm.states[clkIndex]

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
            con.stDependentDrives.append(tir.valuesInTime[0].data.next.drivers[0])

        if tir.timeOffset == INVARIANT_TIME:
            return

        clkPeriod = self.normalizedClkPeriod
        _endClkI = self._endClkI

        assert len(tir.valuesInTime) == 1, ("Value must not be used yet because we need to set persistence ranges first.", tir)

        if not tir.persistenceRanges and tir.timeOffset is not INVARIANT_TIME:
            # value for the first clock behind this clock period and the rest is persistent in this register
            nextClkI = start_clk(tir.timeOffset, clkPeriod) + 1
            if nextClkI <= _endClkI:
                tir.markPersistent(nextClkI, _endClkI)

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
        for nodes in self.fsm.states:
            for node in nodes:
                if isinstance(node, HlsNetNodeWrite):
                    if node.dst is not None:
                        self._initNopValsOfIoForHwIO(node.dst, INTF_DIRECTION.MASTER)

                elif isinstance(node, HlsNetNodeRead):
                    if node.src is not None:
                        self._initNopValsOfIoForHwIO(node.src, INTF_DIRECTION.SLAVE)

    def _collectLoopsAndSetBackedgesToReg(self):
        localControlReads: SetList[HlsNetNodeReadAnyChannel] = SetList()
        controlToStateI: Dict[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel], int] = {}
        clkPeriod = self.normalizedClkPeriod
        for stI, nodes in enumerate(self.fsm.states):
            for node in nodes:
                node: HlsNetNode
                if isinstance(node, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge)):
                    node: HlsNetNodeReadBackedge
                    wr = node.associatedWrite
                    if wr in self._subNodes and wr.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
                        # is in the same arch. element
                        # allocate as a register because this is just local control channel
                        wr.allocationType = BACKEDGE_ALLOCATION_TYPE.REG

                elif isinstance(node, HlsNetNodeLoopStatus):
                    for g in node.fromReenter:
                        e = g.getChannelWhichIsUsedToImplementControl().associatedRead
                        assert isinstance(e, HlsNetNodeReadBackedge), e
                        assert e in self._subNodes, e
                        if e.associatedWrite in self._subNodes:
                            localControlReads.append(e)
                            controlToStateI[e] = stI
                            wr = e.associatedWrite
                            wrTime = max(wr.scheduledIn, default=wr.scheduledZero)
                            controlToStateI[e.associatedWrite] = indexOfClkPeriod(wrTime, clkPeriod)

                    # for g in node.fromExitToHeaderNotify:
                    #    w = g.getChannelWhichIsUsedToImplementControl()
                    #    r = w.associatedRead
                    #    if isinstance(r, HlsNetNodeReadBackedge):
                    #        assert r in self._subNodes, e
                    #        if w in self._subNodes:
                    #            raise NotImplementedError("Convert loop to FSM transitions")
                    #        # dstI =
        return localControlReads, controlToStateI

    def _collectStatesWhichCanNotBeSkipped(self) -> Set[int]:
        # element: clockTickIndex
        clkPeriod = self.normalizedClkPeriod
        nonSkipableStateI: Set[int] = set()
        otherElmConnectionFirstTimeSeen: Dict[ArchElement, int] = {}
        for o, uses, outTime in zip(self._outputs, self.usedBy, self.scheduledOut):
            o: HlsNetNodeOut
            clkI = start_clk(outTime, clkPeriod)
            if not self.fsm.hasUsedStateForClkI(clkI):
                raise AssertionError("fsm is missing state for time where node is scheduled", o, clkI)
            for i in uses:
                otherElm: ArchElement = i.obj
                curFistCommunicationStI = otherElmConnectionFirstTimeSeen.get(otherElm, None)
                if curFistCommunicationStI is None:
                    otherElmConnectionFirstTimeSeen[otherElm] = clkI
                elif curFistCommunicationStI == clkI:
                    continue
                elif curFistCommunicationStI > clkI:
                    otherElmConnectionFirstTimeSeen[otherElm] = clkI
                    nonSkipableStateI.add(curFistCommunicationStI)
                else:
                    nonSkipableStateI.add(clkI)

        return nonSkipableStateI

    def _resolveTranstitionTableFromLoopControlChannels(self,
                localControlReads: SetList[HlsNetNodeReadBackedge],
                controlToStateI: Dict[Union[HlsNetNodeReadBackedge, HlsNetNodeWriteBackedge], int],
                nonSkipableStateI: Set[int]):
        transitionTable = self.transitionTable
        assert not transitionTable, "This should be called only once"
        usedStates = []
        for clkI, st in enumerate(self.fsm.states):
            if st:
                usedStates.append(clkI)

        prev = None
        for isLast, clkI in iter_with_last(usedStates):
            transitionTable[prev] = {clkI: 1}  # jump to next by default
            if isLast:
                transitionTable[clkI] = {usedStates[0]: 1}  # jump back to start by default
            prev = clkI

        for r in localControlReads:
            r: HlsNetNodeReadBackedge
            assert r.associatedWrite in self._subNodes, r
            srcStI = controlToStateI[r.associatedWrite]
            dstStI = controlToStateI[r]
            possible = True
            if dstStI >= srcStI:
                # check if there is any state between these two which can not be skipped
                for i in range(srcStI, dstStI):
                    if i in nonSkipableStateI:
                        possible = False
                        break
            else:
                # check that there is no non optional state behind this state
                for i in range(srcStI, len(self.fsm.states)):
                    if i in nonSkipableStateI:
                        possible = False
                        break
            if not possible:
                continue
            curTrans = transitionTable[srcStI].get(dstStI, None)
            # [fixme] we do not know for sure that IO in skipped states has cond as a skipWhen condition
            #         and thus it may be required to enter dstState
            if r.hasValid():
                condO = r._valid
            elif r.hasValidNB():
                condO = r._validNB
            else:
                condO = r.getValidNB()
                # assert not HdlType_isVoid(r._outputs[0]._dtype), r
                # condO = r._outputs[0]
                # assert condO._dtype.bit_length() == 1, (condO, condO._dtype)

            cond = self.rtlAllocHlsNetNodeOut(condO).valuesInTime[0].data.next
            if curTrans is not None:
                cond = cond | curTrans
            transitionTable[srcStI][dstStI] = cond

        self.stateEncoding = {clkI: i for i, clkI in enumerate(usedStates)}

    def _detectStateTransitions(self):
        """
        Detect the state propagation logic and resolve how to replace it wit a state bit
        * state bit will be just stored as a register in this FSM
        * read will just read this bit
        * write will set this bit to a value specified in write src if all write conditions are meet
        * if the value written to channel is 1 it means that FSM jump to state where associated read is
          There could be multiple channels written but the 1 should be written to just single one
        * All control channel registers which are not written but do have scheduled potential write in this state must be set to 0
        * Because the control channel is just local it is safe to replace it with register.
          However we must keep it in allNodes list so the node is still registered for this element

        :note: This must be called before construction of data-path because we need to resolve how control channels will be realized
        :note: The state transition can not be extracted if there is communication with some other FSM
            which already have some communication with this FSM. (In order to prevent deadlock.)
        """
        localControlReads, controlToStateI = self._collectLoopsAndSetBackedgesToReg()
        nonSkipableStateI = self._collectStatesWhichCanNotBeSkipped()
        self._resolveTranstitionTableFromLoopControlChannels(localControlReads, controlToStateI, nonSkipableStateI)

    @override
    def rtlStatesMayHappenConcurrently(self, stateClkI0: int, stateClkI1: int):
        return stateClkI0 == stateClkI1

    @override
    def rtlAllocDatapathRead(self, node: HlsNetNodeRead, con: ConnectionsOfStage, rtl: List[HdlStatement],
                              validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
        if isinstance(node, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge)) and \
                node.associatedWrite is not None and \
                node.associatedWrite.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
            # nodes of this type are just registers and do not have any IO
            return
        self._rtlAllocDatapathIo(node.src, node, con, rtl, True, validHasCustomDriver, readyHasCustomDriver)

    @override
    def rtlAllocDatapathWrite(self, node: HlsNetNodeWrite, con: ConnectionsOfStage, rtl: List[HdlStatement],
                              validHasCustomDriver:bool=False, readyHasCustomDriver:bool=False):
        if isinstance(node, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)) and\
                node.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
            con.stDependentDrives.extend(rtl)
            # nodes of this type are just registers and do not have any IO
            return
        self._rtlAllocDatapathIo(node.dst, node, con, rtl, False, validHasCustomDriver, readyHasCustomDriver)

    @override
    def rtlAllocDatapath(self):
        """
        Instantiate logic in the states

        :note: This function does not perform efficient register allocations.
            Instead each value is store in individual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
        """
        self._detectStateTransitions()

        for (nodes, con) in zip(self.fsm.states, self.connections):
            con: ConnectionsOfStage
            for node in nodes:
                node: HlsNetNode
                if node._isRtlAllocated:
                    continue
                assert node.scheduledIn is not None, ("Node must be scheduled", node)
                assert node.dependsOn is not None, ("Node must not be destroyed", node)
                node.rtlAlloc(self)

        for con in self.connections:
            if con is None:
                continue
            for rtl in self._rtlAllocIoMux(con.ioMuxes, con.ioMuxesKeysOrdered):
                con.stDependentDrives.extend(rtl)

    @override
    def rtlAllocSync(self):
        self._initNopValsOfIo()
        stateCnt = sum(1 if st else 0 for st in self.fsm.states)
        if stateCnt > 1:
            # if there is more than 1 state
            stReg = self._reg(f"{self.name}st",
                           HBits(log2ceil(max(self.stateEncoding.values()) + 1)),
                           def_val=0)
        else:
            # because there is just a single state, the state value has no meaning
            stReg = None
        # instantiate control of the FSM

        # used to prevent duplication of registers which are just latching the value
        # without modification through multiple stages
        seenRegs: Set[TimeIndependentRtlResourceItem] = set()

        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        usedClks = iter([clkI for clkI, con in enumerate(self.connections) if con is not None])
        next(usedClks, None)  # skip first
        for clkI, con in enumerate(self.connections):
            if not self.fsm.hasUsedStateForClkI(clkI):
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
                        con.stDependentDrives.append(nextStVal.data.next.drivers[0])
                        seenRegs.add(nextStVal)

            unconditionalTransSeen = False
            inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            sync = self._rtlAllocateSyncStreamNode(con)

            # prettify stateAck signal name if required
            stateAck = sync.ack()

            # reduce if ack is a constant value
            if isinstance(stateAck, (bool, int, HConst)):
                assert bool(stateAck) == 1, ("If synchronization of state is always stalling it should be already optimized out", self, clkI)
                stateAck = None
            else:
                assert stateAck._dtype.bit_length() == 1, (stateAck, self, clkI)

            stI = self.stateEncoding[clkI]
            # and ack with state en, to assert that
            if stReg is not None:
                stEn = stReg._eq(stI)
                stateAck = RtlSignalBuilder.buildAndOptional(stateAck, stEn)
                if con.stageEnable is not None:
                    con.stageEnable(stEn)
            elif con.stageEnable is not None:
                con.stageEnable(1)

            # update con.syncNodeAck
            if stateAck is None:
                if con.syncNodeAck is not None:
                    assert not con.syncNodeAck.drivers
                    con.syncNodeAck(1)
            else:
                if con.syncNodeAck is None:
                    con.syncNodeAck = stateAck = rename_signal(self.netlist.parentHwModule, stateAck, f"{self.name}st{clkI:d}_ack")
                else:
                    assert not con.syncNodeAck.drivers
                    con.syncNodeAck(stateAck)
                    stateAck = con.syncNodeAck

            # build next state logic from transitionTable
            # :note: isinstance(x[1], int) to have unconditional transitions as last
            for dstStI, c in sorted(self.transitionTable[clkI].items(), key=lambda tr: (isinstance(tr[1], (int, HBitsConst)), tr[0])):
                assert not unconditionalTransSeen, "If there is an unconditional transition from this state it must be the last one"
                if c == 1:
                    unconditionalTransSeen = True
                    c = stateAck

                elif isinstance(c, (bool, int)):
                    assert c == 0, c
                    continue
                else:
                    assert c._dtype.bit_length() == 1, c
                    c = RtlSignalBuilder.buildAndOptional(c, stateAck)

                if stReg is not None:
                    if c is None:
                        c = True
                    inStateTrans.append((c, stReg(self.stateEncoding[dstStI])))

            stDependentDrives = con.stDependentDrives

            if stateAck is not None:
                # if stateAck is not always satisfied create parent if to load registers conditionally
                stDependentDrives = If(stateAck, stDependentDrives)

            stateTrans.append((stI, [SwitchLogic(inStateTrans),
                                     stDependentDrives,
                                     sync.sync()]))

        self._rtlSyncAllocated = True

        if stReg is None:
            # do not create a state switch statement is there is no state register (and FSM has just 1 state)
            assert len(stateTrans) == 1
            return stateTrans[0][1]
        else:
            return Switch(stReg).add_cases(stateTrans)
