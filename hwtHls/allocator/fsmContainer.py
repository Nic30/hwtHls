from typing import List, Set, Tuple, Optional, Union, Dict

from hwt.code import SwitchLogic, Switch
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.interfaces.std import Signal, HandshakeSync
from hwt.math import log2ceil
from hwt.pyUtils.uniqList import UniqList
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.allocator.connectionsOfStage import getIntfSyncSignals, \
    setNopValIfNotSet, SignalsOfStages, ConnectionsOfStage
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import IoFsm
from hwtHls.netlist.nodes.io import HlsNetNodeWrite, HlsNetNodeRead
from hwtHls.netlist.nodes.node import HlsNetNode
from ipCorePackager.constants import INTF_DIRECTION
from hwtHls.netlist.nodes.backwardEdge import HlsNetNodeReadBackwardEdge, \
    HlsNetNodeWriteBackwardEdge


class AllocatorFsmContainer(AllocatorArchitecturalElement):
    """
    Container class for FSM allocation objects.
    """

    def __init__(self, parentHls: "HlsPipeline", namePrefix:str, fsm: IoFsm):
        allNodes = UniqList()
        for nodes in fsm.states:
            allNodes.extend(nodes)
        self.fsm = fsm
        clkPeriod = self.normalizedClkPeriod = parentHls.normalizedClkPeriod
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
        AllocatorArchitecturalElement.__init__(self, parentHls, namePrefix, allNodes, stateCons, stageSignals)

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
        epsilon = self.parentHls.scheduler.epsilon
        for s in cons:
            s: TimeIndependentRtlResource

            if not s.persistenceRanges and s.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
                self.stageSignals.getForTime(s.timeOffset + epsilon).append(s)
                # value for the first clock behind this clock period and the rest is persistent in this register
                nextClkI = start_clk(s.timeOffset, clkPeriod) + 2
                if nextClkI <= fsmEndClk_i:
                    s.persistenceRanges.append((nextClkI, fsmEndClk_i))

    def _initNopValsOfIo(self):
        """
        initialize nop value which will drive the IO when not used
        """
        for nodes in self.fsm.states:
            for node in nodes:
                if isinstance(node, HlsNetNodeWrite):
                    intf = node.dst
                    # to prevent latching when interface is not used
                    syncSignals = getIntfSyncSignals(intf)
                    setNopValIfNotSet(intf, None, syncSignals)

                elif isinstance(node, HlsNetNodeRead):
                    intf = node.src
                    syncSignals = getIntfSyncSignals(intf)

                else:
                    syncSignals = None

                if syncSignals is not None:
                    for s in syncSignals:
                        setNopValIfNotSet(s, 0, ())

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
                        node.associated_write.allocateAsBuffer = False # allocate as a register because this is just local controll channel
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
            for node in nodes:
                node: HlsNetNode
                rtl = node.allocateRtlInstance(self)

                if isinstance(node, HlsNetNodeRead):
                    if isinstance(node, HlsNetNodeReadBackwardEdge) and not node.associated_write.allocateAsBuffer:
                        continue
                    if not isinstance(node.src, (Signal, RtlSignal)):
                        # if it has some synchronization
                        con.inputs.append(node.src)
                    self._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond)

                elif isinstance(node, HlsNetNodeWrite):
                    if isinstance(node, HlsNetNodeWriteBackwardEdge) and not node.allocateAsBuffer:
                        continue
                    con.stDependentDrives.append(rtl)
                    if not isinstance(node.dst, (Signal, RtlSignal)):
                        # if it has some synchronization
                        con.outputs.append(node.dst)
                    self._copy_sync(node.dst, node, con.io_skipWhen, con.io_extraCond)

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
            for dstSt, c in sorted(fsm.transitionTable[stI].items(), key=lambda x: x[0]):
                assert not unconditionalTransSeen
                ack = sync.ack()
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
