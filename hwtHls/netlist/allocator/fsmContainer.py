from typing import List, Set, Tuple, Optional, Union, Dict

from hwt.code import SwitchLogic, Switch
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.interfaces.std import HandshakeSync
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.interface import Interface
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.netlist.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.netlist.allocator.connectionsOfStage import getIntfSyncSignals, \
    setNopValIfNotSet, SignalsOfStages, ConnectionsOfStage
from hwtHls.netlist.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.scheduler.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import IoFsm
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge
from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead
from hwtHls.netlist.nodes.node import HlsNetNode
from ipCorePackager.constants import INTF_DIRECTION


class AllocatorFsmContainer(AllocatorArchitecturalElement):
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
        AllocatorArchitecturalElement.__init__(self, netlist, namePrefix, allNodes, stateCons, stageSignals)

    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        # mark value in register as persistent until the end of FSM
        isTir = isinstance(rtl, TimeIndependentRtlResource)
        if rtl is None or not isTir:
            cons = (self.netNodeToRtl[o] for o in n._outputs if o in self.netNodeToRtl)
        elif isTir and rtl.timeOffset == TimeIndependentRtlResource.INVARIANT_TIME:
            return
        else:
            cons = (rtl,)

        clkPeriod = self.normalizedClkPeriod
        fsmEndClk_i = self.fsmEndClk_i

        for s in cons:
            s: TimeIndependentRtlResource
            assert len(s.valuesInTime) == 1, ("Value must not be used yet because we need to set persistence ranges first.", s)

            if not s.persistenceRanges and s.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
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

        con = self.connections[stateI]

        if intfDir == INTF_DIRECTION.MASTER:
            con.outputs.append(intf)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, intfDir
            con.inputs.append(intf)
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
        localControlReads: UniqList[HlsNetNodeReadBackwardEdge] = UniqList()
        controlToStateI: Dict[Union[HlsNetNodeReadBackwardEdge, HlsNetNodeWriteBackwardEdge]] = {}
        for stI, nodes in enumerate(self.fsm.states):
            for node in nodes:
                node: HlsNetNode
                if isinstance(node, HlsNetNodeReadBackwardEdge):
                    node: HlsNetNodeReadBackwardEdge
                    if node.associated_write in self.allNodes:
                        localControlReads.append(node)
                        node.associated_write.allocateAsBuffer = False  # allocate as a register because this is just local controll channel
                        controlToStateI[node] = stI

                elif isinstance(node, HlsNetNodeWriteBackwardEdge):
                    if node.associated_read in self.allNodes:
                        controlToStateI[node] = stI

        for r in localControlReads:
            r: HlsNetNodeReadBackwardEdge
            srcStI = controlToStateI[r.associated_write]
            dstStI = controlToStateI[r]
            curTrans = self.fsm.transitionTable[srcStI].get(dstStI, None)
            cond = self.instantiateHlsNetNodeOut(r._outputs[0]).valuesInTime[0].data.next
            if curTrans is not None:
                cond = cond | curTrans
            self.fsm.transitionTable[srcStI][dstStI] = cond
        # detect the state propagation logic and resolve how to replace it wit a state bit
        # * state bit will be just stored as a register in this fsm
        # * read will just read this bit
        # * write will set this bit to a value specified in write src if all write conditions are meet

        # * if the value writen to channel is 1 it means that fsm jump to state where associated read is
        #   There could be multiple channels written but the 1 should be writen to just 1
        # * Because the control channel is just local it is safe to replace it
        #   However we must keep it in allNodes list so the node is still registered for this element

    def allocateDataPath(self, iea: "InterArchElementNodeSharingAnalysis"):
        """
        Instantiate logic in the states

        :note: This function does not perform efficient register allocations.
            Instead each value is store in individual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
        """
        self.interArchAnalysis = iea
        self._detectStateTransitions()
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
                    self._allocateIo(node.src, node, con, ioMuxes, ioSeen, rtl)

                elif isinstance(node, HlsNetNodeWrite):
                    if isinstance(node, HlsNetNodeWriteBackwardEdge) and not node.allocateAsBuffer:
                        con.stDependentDrives.append(rtl)
                        continue
                    self._allocateIo(node.dst, node, con, ioMuxes, ioSeen, rtl)

            for rtl in self._allocateIoMux(ioMuxes, ioSeen):
                con.stDependentDrives.append(rtl)

    def allocateSync(self):
        fsm = self.fsm
        self._initNopValsOfIo()
        st = self._reg(f"{self.namePrefix}st_{fsm.intf._name}",
                       Bits(log2ceil(len(fsm.states)), signed=False),
                       def_val=0)

        # instantiate control of the FSM

        # used to prevent duplication of registes which are just latching the value
        # without modification throught multiple stages
        seenRegs: Set[TimeIndependentRtlResource] = set()

        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        for stI, con in enumerate(self.connections):
            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(self.fsmBeginClk_i + stI + 1)
                if v is not None and v.is_rlt_register() and not v in seenRegs:
                    con.stDependentDrives.append(v.data.next.drivers[0])
                    seenRegs.add(v)

            unconditionalTransSeen = False
            inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            sync = self._makeSyncNode(con)
            ack = sync.ack()
            for dstSt, c in sorted(fsm.transitionTable[stI].items(), key=lambda x: x[0]):
                assert not unconditionalTransSeen, "If there is an unconditional transition it must be last"
                if isinstance(ack, (bool, int)):
                    c = c & ack
                else:
                    c = ack & c
                if c == 1:
                    unconditionalTransSeen = True
                    inStateTrans.append((c, st(dstSt)))
                else:
                    inStateTrans.append((c, st(dstSt)))

            stateTrans.append((stI, [SwitchLogic(inStateTrans),
                                     con.stDependentDrives,
                                     sync.sync()]))

        return Switch(st).add_cases(stateTrans)
