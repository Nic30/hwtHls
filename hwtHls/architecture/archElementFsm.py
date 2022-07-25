from typing import List, Set, Tuple, Optional, Union, Dict

from hwt.code import SwitchLogic, Switch, If
from hwt.code_utils import rename_signal
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
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
from hwtHls.netlist.analysis.fsm import IoFsm
from hwtHls.netlist.analysis.io import HlsNetlistAnalysisPassDiscoverIo
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge, HlsNetNodeReadControlBackwardEdge, \
    HlsNetNodeWriteControlBackwardEdge
from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ports import HlsNetNodeOut
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.scheduler.clk_math import start_clk
from ipCorePackager.constants import INTF_DIRECTION


class ArchElementFsm(ArchElement):
    """
    Container class for FSM allocation objects.
    """

    def __init__(self, netlist: "HlsNetlistCtx", namePrefix:str, fsm: IoFsm):
        allNodes = UniqList()
        for nodes in fsm.states:
            allNodes.extend(nodes)
        self.fsm = fsm
        clkPeriod = self.normalizedClkPeriod = netlist.normalizedClkPeriod
        assert fsm.states, fsm

        self.fsmEndClk_i = max(fsm.stateClkI.values())
        self.fsmBeginClk_i = min(fsm.stateClkI.values())
        self.clkIToStateI = clkIToStateI = {v:k for k, v in fsm.stateClkI.items()}

        stateCons = [ConnectionsOfStage() for _ in fsm.states]
        stageSignals = SignalsOfStages(clkPeriod,
                                        (
                                           stateCons[clkIToStateI[clkI]].signals if clkI in clkIToStateI else None
                                           for clkI in range(self.fsmEndClk_i + 1)
                                        ))
        ArchElement.__init__(self, netlist, namePrefix, allNodes, stateCons, stageSignals)

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        # mark value in register as persistent until the end of FSM
        isTir = isinstance(rtl, TimeIndependentRtlResource)
        if isinstance(n, HlsProgramStarter):
            assert isTir, n
            # because we want to consume token from the starter only on transition in this FSM
            con: ConnectionsOfStage = self.connections[0]
            con.stDependentDrives.append(rtl.valuesInTime[0].data.next.drivers[0])

        if rtl is None or not isTir:
            cons = (self.netNodeToRtl[o] for o in n._outputs if o in self.netNodeToRtl)
        elif isTir and rtl.timeOffset == INVARIANT_TIME:
            return
        else:
            cons = (rtl,)

        clkPeriod = self.normalizedClkPeriod
        fsmEndClk_i = self.fsmEndClk_i

        for s in cons:
            s: TimeIndependentRtlResource
            assert len(s.valuesInTime) == 1, ("Value must not be used yet because we need to set persistence ranges first.", s)

            if not s.persistenceRanges and s.timeOffset is not INVARIANT_TIME:
                self.stageSignals.getForTime(s.timeOffset).append(s)
                # value for the first clock behind this clock period and the rest is persistent in this register
                nextClkI = start_clk(s.timeOffset, clkPeriod) + 2
                if nextClkI <= fsmEndClk_i:
                    s.persistenceRanges.append((nextClkI, fsmEndClk_i))

        for dep in n.dependsOn:
            self._afterOutputUsed(dep)

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        try:
            stateI = self.clkIToStateI[clkI]
        except KeyError:
            raise AssertionError("Asking for a sync in an element which is not scheduled in this clk period", self, clkI, self.clkIToStateI)

        con: ConnectionsOfStage = self.connections[stateI]
        self._connectSync(con, intf, intfDir)
        self._initNopValsOfIoForIntf(intf, intfDir)

    def _initNopValsOfIoForIntf(self, intf: Interface, intfDir: INTF_DIRECTION):
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

    def _detectStateTransitions(self):
        """
        Detect the state propagation logic and resolve how to replace it wit a state bit
        * state bit will be just stored as a register in this FSM
        * read will just read this bit
        * write will set this bit to a value specified in write src if all write conditions are meet
        * if the value written to channel is 1 it means that FSM jump to state where associated read is
          There could be multiple channels written but the 1 should be written to just single one
        * All control channel registers which are not written but do have scheduled potential write in this state must be set to 0
        * Because the control channel is just local it is safe to replace it
          However we must keep it in allNodes list so the node is still registered for this element
        
        :note: This must be called before construction of data-path because we need to resolve how control channels will be realized
        :note: The state transition can not be extracted if there is communication with some other FSM
            which already have some communication with this FSM. (In order to prevent deadlock.)
        """
        localControlReads: UniqList[HlsNetNodeReadControlBackwardEdge] = UniqList()
        controlToStateI: Dict[Union[HlsNetNodeReadControlBackwardEdge, HlsNetNodeWriteControlBackwardEdge], int] = {}
        for stI, nodes in enumerate(self.fsm.states):
            for node in nodes:
                node: HlsNetNode
                if isinstance(node, HlsNetNodeReadBackwardEdge):
                    node: HlsNetNodeReadBackwardEdge
                    if node.associated_write in self.allNodes:  # is in the same arch. element
                        node.associated_write.allocateAsBuffer = False  # allocate as a register because this is just local control channel
                        if isinstance(node, HlsNetNodeReadControlBackwardEdge):
                            localControlReads.append(node)
                            controlToStateI[node] = stI

                elif isinstance(node, HlsNetNodeWriteControlBackwardEdge):
                    if node.associated_read in self.allNodes:
                        controlToStateI[node] = stI
        
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
                stI = self.clkIToStateI[clkI]
                for otherElm in self.interArchAnalysis.ownerOfInput[i]:
                    curFistCommunicationStI = otherElmConnectionFirstTimeSeen.get(otherElm, None)
                    if curFistCommunicationStI is None:
                        otherElmConnectionFirstTimeSeen[otherElm] = stI
                    elif curFistCommunicationStI == stI:
                        continue
                    else:
                        if curFistCommunicationStI > stI:
                            otherElmConnectionFirstTimeSeen[otherElm] = stI
                            nonSkipableStateI.add(curFistCommunicationStI)
                        else:
                            nonSkipableStateI.add(stI)

        transitionTable = self.fsm.transitionTable
        for r in localControlReads:
            r: HlsNetNodeReadControlBackwardEdge
            srcStI = controlToStateI[r.associated_write]
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
            cond = self.instantiateHlsNetNodeOut(r._outputs[0]).valuesInTime[0].data.next
            if curTrans is not None:
                cond = cond | curTrans
            transitionTable[srcStI][dstStI] = cond

    def allocateDataPath(self, iea: "InterArchElementNodeSharingAnalysis"):
        """
        Instantiate logic in the states

        :note: This function does not perform efficient register allocations.
            Instead each value is store in individual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
        """
        self.interArchAnalysis = iea
        self._detectStateTransitions()
        ioDiscovery: HlsNetlistAnalysisPassDiscoverIo = self.netlist.getAnalysis(HlsNetlistAnalysisPassDiscoverIo)

        for (nodes, con) in zip(self.fsm.states, self.connections):
            ioMuxes: Dict[Interface, Tuple[Union[HlsNetNodeRead, HlsNetNodeWrite], List[HdlStatement]]] = {}
            ioSeen: UniqList[Interface] = UniqList()
            for node in nodes:
                node: HlsNetNode
                wasInstantiated = node._outputs and node._outputs[0] not in self.netNodeToRtl
                rtl = node.allocateRtlInstance(self)
                if wasInstantiated:
                    self._afterNodeInstantiated(node, rtl)

                if isinstance(node, HlsNetNodeRead):
                    if isinstance(node, HlsNetNodeReadBackwardEdge) and not node.associated_write.allocateAsBuffer:
                        continue
                    self._allocateIo(ioDiscovery, node.src, node, con, ioMuxes, ioSeen, rtl)

                elif isinstance(node, HlsNetNodeWrite):
                    if isinstance(node, HlsNetNodeWriteBackwardEdge) and not node.allocateAsBuffer:
                        con.stDependentDrives.append(rtl)
                        continue
                    self._allocateIo(ioDiscovery, node.dst, node, con, ioMuxes, ioSeen, rtl)
                #elif isinstance(node, HlsNetNodeExplicitSync):
                    # * this sync is not associated with any IO and thus no sync is required
                    #   * if this sync is associated with multiple reads this is an invalid state
                    # * this sync is associated with read scheduled in this clock cycle
                    # if this sync is associated with read in prev clock cycle, this may result in deadlock due to need for read
                    # if this sync is associated with write, this should already have been merged
                    #raise NotImplementedError()

            for rtl in self._allocateIoMux(ioMuxes, ioSeen):
                con.stDependentDrives.append(rtl)
        
    def allocateSync(self):
        fsm = self.fsm
        self._initNopValsOfIo()
        if len(fsm.states) > 1:
            st = self._reg(f"{self.namePrefix}st",
                           Bits(log2ceil(len(fsm.states)), signed=False),
                           def_val=0)
        else:
            # because there is just a single state, the state value has no meaning
            st = None
        # instantiate control of the FSM

        # used to prevent duplication of registers which are just latching the value
        # without modification through multiple stages
        seenRegs: Set[TimeIndependentRtlResource] = set()

        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        for stI, con in enumerate(self.connections):
            con: ConnectionsOfStage
            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(self.fsmBeginClk_i + stI + 1)
                if v is not None and v.is_rlt_register() and not v in seenRegs:
                    con.stDependentDrives.append(v.data.next.drivers[0])
                    seenRegs.add(v)

            unconditionalTransSeen = False
            inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            sync = self._makeSyncNode(None, con)
            stateAck = sync.ack()
            if isinstance(stateAck, (bool, int, HValue)):
                assert bool(stateAck) == 1
            else:
                stateAck = rename_signal(self.netlist.parentUnit, stateAck, f"{self.namePrefix}st_{stI:d}_ack")
            con.syncNodeAck = stateAck
            
            for dstSt, c in sorted(fsm.transitionTable[stI].items(), key=lambda x: x[0]):
                assert not unconditionalTransSeen, "If there is an unconditional transition from this state it must be the last one"
                if isinstance(stateAck, (bool, int)):
                    c = c & stateAck
                else:
                    c = stateAck & c
                if c == 1:
                    unconditionalTransSeen = True

                if st is not None:
                    inStateTrans.append((c, st(dstSt)))
            
            stDependentDrives = con.stDependentDrives

            if isinstance(stateAck, (bool, int)):
                assert bool(stateAck) == 1
            else:
                stDependentDrives = If(stateAck, stDependentDrives)

            stateTrans.append((stI, [SwitchLogic(inStateTrans),
                                     stDependentDrives,
                                     sync.sync()]))

        if st is None:
            assert len(stateTrans) == 1
            return stateTrans[0][1]
        else:
            return Switch(st).add_cases(stateTrans)
