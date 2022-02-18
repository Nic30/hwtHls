from itertools import chain
from typing import List, Set, Tuple, Optional

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


class AllocatorFsmContainer(AllocatorArchitecturalElement):
    """
    Contaner class for FSM allocation objects.
    """

    def __init__(self, parentHls: "HlsPipeline", namePrefix:str, fsm: IoFsm):
        allNodes = UniqList()
        for nodes in fsm.states:
            allNodes.extend(nodes)
        self.fsm = fsm
        clk_period = self.clk_period = parentHls.clk_period
        assert fsm.states, fsm

        self.fsmEndClk_i = max(fsm.stateClkI.values())
        startTime = min(min(chain(node.scheduledIn, node.scheduledOut)) for node in fsm.states[0])
        self.fsmBeginClk_i = int(startTime // clk_period)
        self.clkIToStateI = clkIToStateI = {v:k for k, v in fsm.stateClkI.items()}

        stateCons = [ConnectionsOfStage() for _ in fsm.states]
        stageSignals = SignalsOfStages(clk_period, startTime,
                                       (
                                           stateCons[clkIToStateI[clkI]].signals if clkI in clkIToStateI else None
                                           for clkI in range(self.fsmEndClk_i + 1)
                                        ))
        AllocatorArchitecturalElement.__init__(self, parentHls, namePrefix, allNodes, stateCons, stageSignals)

    def connectSync(self, clkI: int, intf: HandshakeSync, intfDir: INTF_DIRECTION):
        con = self.connections[self.clkIToStateI[clkI]]
        if intfDir == INTF_DIRECTION.MASTER:
            con.outputs.append(intf)
        else:
            assert intfDir == INTF_DIRECTION.SLAVE, intfDir
            con.inputs.append(intf)
        
    def _afterNodeInstantiated(self, n: HlsNetNode, rtl: Optional[TimeIndependentRtlResource]):
        # mark value in register as persisten until the end of fsm
        isTir = isinstance(rtl, TimeIndependentRtlResource)
        if rtl is None or not isTir:
            cons = (self.netNodeToRtl[o] for o in n._outputs if o in self.netNodeToRtl)
        elif isTir and rtl.timeOffset == TimeIndependentRtlResource.INVARIANT_TIME:
            return 
        else:
            cons = (rtl,)

        clk_period = self.clk_period
        fsmEndClk_i = self.fsmEndClk_i
        for s in cons:
            s: TimeIndependentRtlResource
            self.stageSignals.getForTime(s.timeOffset).append(s)
            
            if not s.persistenceRanges and s.timeOffset is not TimeIndependentRtlResource.INVARIANT_TIME:
                # val for the first clock behind this is int the register and the rest is persistent
                nextClkI = start_clk(s.timeOffset, clk_period) + 2
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

    def allocateDataPath(self):
        """
        Instantiate logic in the states

        :note: This function does not perform efficient register allocations.
            Instead each value is store in idividual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
        """
        for (nodes, con) in zip(self.fsm.states, self.connections):
            for node in nodes:
                node: HlsNetNode
                rtl = node.allocateRtlInstance(self)

                if isinstance(node, HlsNetNodeRead):
                    if not isinstance(node.src, (Signal, RtlSignal)):
                        # if it has some synchronization
                        con.inputs.append(node.src)
                    self._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond)

                elif isinstance(node, HlsNetNodeWrite):
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
                c = sync.ack() & c
                if c == 1:
                    unconditionalTransSeen = True
                    inStateTrans.append((c, st(dstSt)))
                else:
                    inStateTrans.append((c, st(dstSt)))
            stateTrans.append((stI, [SwitchLogic(inStateTrans),
                                     con.stDependentDrives,
                                     sync.sync()]))

        return Switch(st).add_cases(stateTrans)
