from typing import List, Set, Tuple, Optional, Union, Dict, Generator

from hwt.code import SwitchLogic, Switch, If
from hwt.code_utils import rename_signal
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.hdl.types.bitsVal import BitsVal
from hwt.hdl.value import HValue
from hwt.interfaces.std import HandshakeSync
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.architecture.archElement import ArchElement
from hwtHls.architecture.connectionsOfStage import getIntfSyncSignals, \
    setNopValIfNotSet, SignalsOfStages, ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, INVARIANT_TIME
from hwtHls.netlist.analysis.detectFsms import IoFsm
from hwtHls.netlist.analysis.ioDiscover import HlsNetlistAnalysisPassIoDiscover
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge, BACKEDGE_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode, HlsNetNodePartRef
from hwtHls.netlist.nodes.orderable import HdlType_isNonData, HdlType_isVoid
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import  HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import start_clk, indexOfClkPeriod
from ipCorePackager.constants import INTF_DIRECTION
from hdlConvertorAst.to.hdlUtils import iter_with_last


class ArchElementFsm(ArchElement):
    """
    Container class for FSM allocation objects.

    :ivar fsm: an original IoFsm object from which this was created
    :ivar transitionTable: a dictionary source stateI to dictionary destination stateI to condition for transition
    :ivar stateEncoding: a dictionary mapping state index to a value which will be used in RTL to represent this state.
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str, fsm: IoFsm):
        allNodes = UniqList()
        for nodes in fsm.states:
            allNodes.extend(nodes)
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

        stateCons = [ConnectionsOfStage() for _ in fsm.states]
        stageSignals = self._createSignalsOfStages(fsm, clkPeriod, stateCons)
        ArchElement.__init__(self, netlist, namePrefix, allNodes, stateCons, stageSignals)
        self._beginClkI = beginClkI
        self._endClkI = endClkI
        self.transitionTable: Dict[int, Dict[int, Union[bool, RtlSignal]]] = {}
        self.stateEncoding: Dict[int, int] = {}

    def iterStages(self) -> Generator[Tuple[int, List[HlsNetNode]], None, None]:
        fsm = self.fsm
        for clkI, nodes in enumerate(fsm.states):
            if nodes:
                yield (clkI, nodes)

    def getStageForClock(self, clkIndex: int) -> List[HlsNetNode]:
        return self.fsm.states[clkIndex]

    @staticmethod
    def _createSignalsOfStages(fsm: IoFsm, clkPeriod: int, stateCons: List[ConnectionsOfStage]):
        return SignalsOfStages(clkPeriod,
                               (
                                  stateCons[clkI].signals
                                  if st else None
                                  for clkI, st in enumerate(fsm.states)
                               ))

    def _iterTirsOfNode(self, n: HlsNetNode) -> Generator[TimeIndependentRtlResource, None, None]:
        for o in n._outputs:
            if o in self.netNodeToRtl and not HdlType_isNonData(o._dtype):
                tirs = self.netNodeToRtl[o]
                if isinstance(tirs, TimeIndependentRtlResource):
                    yield tirs
                else:
                    yield from tirs

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        # mark value in register as persistent until the end of FSM
        isTir = isinstance(rtl, TimeIndependentRtlResource)
        if isinstance(n, HlsProgramStarter):
            assert isTir, n
            # because we want to consume token from the starter only on transition in this FSM
            con: ConnectionsOfStage = self.connections[0]
            con.stDependentDrives.append(rtl.valuesInTime[0].data.next.drivers[0])

        if rtl is None or not isTir:
            cons = self._iterTirsOfNode(n)
        elif isTir and rtl.timeOffset == INVARIANT_TIME:
            return
        else:
            cons = (rtl,)

        clkPeriod = self.normalizedClkPeriod
        _endClkI = self._endClkI

        for s in cons:
            assert isinstance(s, TimeIndependentRtlResource)
            s: TimeIndependentRtlResource
            assert len(s.valuesInTime) == 1, ("Value must not be used yet because we need to set persistence ranges first.", s)

            if not s.persistenceRanges and s.timeOffset is not INVARIANT_TIME:
                self.stageSignals.getForTime(s.timeOffset).append(s)
                # value for the first clock behind this clock period and the rest is persistent in this register
                nextClkI = start_clk(s.timeOffset, clkPeriod) + 2
                if nextClkI <= _endClkI:
                    s.persistenceRanges.append((nextClkI, _endClkI))

        for dep in n.dependsOn:
            self._afterOutputUsed(dep)

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION, isBlocking: bool):
        assert self.fsm.hasUsedStateForClkI(clkI), ("Asking for a sync in an element which is not scheduled in this clk period", self, clkI)

        con: ConnectionsOfStage = self.connections[clkI]
        self._connectSync(con, intf, intfDir, isBlocking)
        self._initNopValsOfIoForIntf(intf, intfDir)
        return con

    def _initNopValsOfIoForIntf(self, intf: Union[Interface], intfDir: INTF_DIRECTION):
        if intfDir == INTF_DIRECTION.MASTER:
            # to prevent latching when interface is not used
            syncSignals = getIntfSyncSignals(intf)
            setNopValIfNotSet(intf, None, syncSignals)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, (intf, intfDir)
            syncSignals = getIntfSyncSignals(intf)

        for s in syncSignals:
            setNopValIfNotSet(s, 0, ())

    def _initNopValsOfIo(self):
        """
        initialize nop value which will drive the IO when not used
        """
        for nodes in self.fsm.states:
            for node in nodes:
                if isinstance(node, HlsNetNodeWrite):
                    self._initNopValsOfIoForIntf(node.dst, INTF_DIRECTION.MASTER)

                elif isinstance(node, HlsNetNodeRead):
                    self._initNopValsOfIoForIntf(node.src, INTF_DIRECTION.SLAVE)

    def _collectLoopsAndSetBackedgesToReg(self):
        localControlReads: UniqList[HlsNetNodeReadBackedge] = UniqList()
        controlToStateI: Dict[Union[HlsNetNodeReadBackedge, HlsNetNodeWriteBackedge], int] = {}
        clkPeriod = self.normalizedClkPeriod
        for stI, nodes in enumerate(self.fsm.states):
            for node in nodes:
                node: HlsNetNode
                if isinstance(node, HlsNetNodeReadBackedge):
                    node: HlsNetNodeReadBackedge
                    wr = node.associatedWrite
                    if wr in self.allNodes and wr.allocationType == BACKEDGE_ALLOCATION_TYPE.BUFFER:
                        # is in the same arch. element
                        # allocate as a register because this is just local control channel
                        wr.allocationType = BACKEDGE_ALLOCATION_TYPE.REG

                elif isinstance(node, HlsNetNodeLoopStatus):
                    for e in node.fromReenter:
                        assert isinstance(e, HlsNetNodeReadBackedge), e
                        assert e in self.allNodes, e
                        if e.associatedWrite in self.allNodes:
                            localControlReads.append(e)
                            controlToStateI[e] = stI
                            controlToStateI[e.associatedWrite] = indexOfClkPeriod(e.associatedWrite.scheduledZero, clkPeriod)

                    for e in node.fromExit:
                        if isinstance(e, HlsNetNodeReadBackedge):
                            assert e in self.allNodes, e
                            if e.associatedWrite in self.allNodes:
                                raise NotImplementedError()
                            # dstI =
        return localControlReads, controlToStateI

    def _collectStatesWhichCanNotBeSkipped(self) -> Set[int]:
        # element: clockTickIndex
        clkPeriod = self.normalizedClkPeriod
        nonSkipableStateI: Set[int] = set()
        otherElmConnectionFirstTimeSeen: Dict[ArchElement, int] = {}
        iea = self.interArchAnalysis
        for o, i in self.interArchAnalysis.interElemConnections:
            o: HlsNetNodeOut
            if self is iea.ownerOfOutput[o]:
                outTime = o.obj.scheduledOut[o.out_i]
                clkI = start_clk(outTime, clkPeriod)
                if not self.fsm.hasUsedStateForClkI(clkI):
                    raise AssertionError("fsm is missing state for time where node is scheduled", o, clkI)

                for otherElm in self.interArchAnalysis.ownerOfInput[i]:
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
                localControlReads: UniqList[HlsNetNodeReadBackedge],
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
            # [fixme] we do not for sure that IO in skipped states has cond as a skipWhen condition
            #         and thus it may be required to enter dstState
            if r.hasValid():
                condO = r._valid
            elif r.hasValidNB():
                condO = r._validNB
            else:
                assert not HdlType_isVoid(r._outputs[0]._dtype), r
                condO = r._outputs[0]
                assert condO._dtype.bit_length() == 1, condO

            cond = self.instantiateHlsNetNodeOut(condO).valuesInTime[0].data.next
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

    def _allocateDataPathRead(self, node: HlsNetNodeRead, ioDiscovery: HlsNetlistAnalysisPassIoDiscover, con: ConnectionsOfStage,
                              ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                              ioSeen: UniqList[Interface],
                              rtl: List[HdlStatement]):
        if isinstance(node, HlsNetNodeReadBackedge) and \
                node.associatedWrite is not None and \
                node.associatedWrite.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
            return
        self._allocateIo(ioDiscovery, node.src, node, con, ioMuxes, ioSeen, rtl)

    def _allocateDataPathWrite(self, node: HlsNetNodeWrite, ioDiscovery: HlsNetlistAnalysisPassIoDiscover, con: ConnectionsOfStage,
                              ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]],
                              ioSeen: UniqList[Interface],
                              rtl: List[HdlStatement]):
        if isinstance(node, HlsNetNodeWriteBackedge) and node.allocationType != BACKEDGE_ALLOCATION_TYPE.BUFFER:
            con.stDependentDrives.append(rtl)
            return
        self._allocateIo(ioDiscovery, node.dst, node, con, ioMuxes, ioSeen, rtl)

    def allocateDataPath(self, iea: "InterArchElementNodeSharingAnalysis"):
        """
        Instantiate logic in the states

        :note: This function does not perform efficient register allocations.
            Instead each value is store in individual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
        """
        self.interArchAnalysis = iea
        self._detectStateTransitions()
        ioDiscovery: HlsNetlistAnalysisPassIoDiscover = self.netlist.getAnalysis(HlsNetlistAnalysisPassIoDiscover)

        for (nodes, con) in zip(self.fsm.states, self.connections):
            con: ConnectionsOfStage
            ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]] = {}
            ioSeen: UniqList[Interface] = UniqList()
            for node in nodes:
                node: HlsNetNode
                wasInstantiated = node._outputs and node._outputs[0] not in self.netNodeToRtl
                rtl = node.allocateRtlInstance(self)
                if wasInstantiated:
                    self._afterNodeInstantiated(node, rtl)

                if isinstance(node, HlsNetNodeRead):
                    self._allocateDataPathRead(node, ioDiscovery, con, ioMuxes, ioSeen, rtl)

                elif isinstance(node, HlsNetNodeWrite):
                    self._allocateDataPathWrite(node, ioDiscovery, con, ioMuxes, ioSeen, rtl)

                elif isinstance(node, HlsNetNodePartRef):
                    for r in node.iterChildReads():
                        self._allocateDataPathRead(r, ioDiscovery, con, ioMuxes, ioSeen, rtl)
                    for w in node.iterChildWrites():
                        self._allocateDataPathWrite(w, ioDiscovery, con, ioMuxes, ioSeen, rtl)

                elif node.__class__ is HlsNetNodeExplicitSync:
                    raise NotImplementedError(node)
                    # this node should already be collected by HlsNetlistAnalysisPassIoDiscover

            for rtl in self._allocateIoMux(ioMuxes, ioSeen):
                con.stDependentDrives.append(rtl)

    def allocateSync(self):
        self._initNopValsOfIo()
        if sum(1 if st else 0 for st in self.fsm.states) > 1:
            stReg = self._reg(f"{self.namePrefix}st",
                           Bits(log2ceil(len(self.fsm.states)), signed=False),
                           def_val=0)
        else:
            # because there is just a single state, the state value has no meaning
            stReg = None
        # instantiate control of the FSM

        # used to prevent duplication of registers which are just latching the value
        # without modification through multiple stages
        seenRegs: Set[TimeIndependentRtlResource] = set()

        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        for clkI, con in enumerate(self.connections):
            con: ConnectionsOfStage
            if not self.fsm.hasUsedStateForClkI(clkI):
                continue

            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(clkI + 1)
                if v is not None and v.isRltRegister() and not v in seenRegs:
                    con.stDependentDrives.append(v.data.next.drivers[0])
                    seenRegs.add(v)

            unconditionalTransSeen = False
            inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            sync = self._makeSyncNode(con)

            # prettify stateAck signal name if required
            stateAck = sync.ack()
            if isinstance(stateAck, (bool, int, HValue)):
                assert bool(stateAck) == 1
            else:
                assert stateAck._dtype.bit_length() == 1
                stateAck = rename_signal(self.netlist.parentUnit, stateAck, f"{self.namePrefix}st{clkI:d}_ack")

            con.syncNodeAck = stateAck
            # :note: isinstance(x[1], int) to have unconditional transitions as last
            for dstStI, c in sorted(self.transitionTable[clkI].items(), key=lambda tr: (isinstance(tr[1], int), tr[0])):
                assert not unconditionalTransSeen, "If there is an unconditional transition from this state it must be the last one"
                if c == 1:
                    unconditionalTransSeen = True
                    c = stateAck
                
                elif isinstance(c, (bool, int)):
                    assert c == 0, c
                    continue
                else:
                    assert c._dtype.bit_length() == 1, c
                    c = c & stateAck
    
                if stReg is not None:
                    inStateTrans.append((c, stReg(dstStI)))

            stDependentDrives = con.stDependentDrives

            if isinstance(stateAck, (bool, int, BitsVal)):
                assert bool(stateAck) == 1, "There should be a transition to some next state."
            else:
                # if stateAck is not always satisfied create parent if to load registers conditionally
                stDependentDrives = If(stateAck, stDependentDrives)

            stI = self.stateEncoding[clkI]
            stateTrans.append((stI, [SwitchLogic(inStateTrans),
                                     stDependentDrives,
                                     sync.sync()]))

        if stReg is None:
            # do not create a state switch statement is there is no state register (and FSM has just 1 state)
            assert len(stateTrans) == 1
            return stateTrans[0][1]
        else:
            return Switch(stReg).add_cases(stateTrans)
