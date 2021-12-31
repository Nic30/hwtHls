from typing import List, Set, Tuple, Dict

from hwt.code import SwitchLogic, Switch
from hwt.hdl.statements.statement import HdlStatement
from hwt.hdl.types.bits import Bits
from hwt.interfaces.std import Signal
from hwt.math import log2ceil
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.allocator.allocator import ConnectionsOfStage
from hwtHls.allocator.architecturalElement import AllocatorArchitecturalElement
from hwtHls.allocator.connectionsOfStage import getIntfSyncSignals, \
    setNopValIfNotSet
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import start_clk
from hwtHls.netlist.analysis.fsm import IoFsm
from hwtHls.netlist.nodes.io import HlsWrite, HlsRead


class FsmContainer(AllocatorArchitecturalElement):

    def __init__(self, allocator: "HlsAllocator", fsm: IoFsm):
        AllocatorArchitecturalElement.__init__(self, allocator)
        self.fsm = fsm

    def _initNopValsOfIo(self):
        # initialize nop value which will drive the IO when not used
        for nodes in self.fsm.states:
            for node in nodes:
                if isinstance(node, HlsWrite):
                    intf = node.dst
                    # to prevent latching when interface is not used
                    syncSignals = getIntfSyncSignals(intf)
                    setNopValIfNotSet(intf, None, syncSignals)
                elif isinstance(node, HlsRead):
                    intf = node.src
                    syncSignals = getIntfSyncSignals(intf)
                else:
                    syncSignals = None
                
                if syncSignals is not None:
                    for s in syncSignals:
                        setNopValIfNotSet(s, 0, ())

    def allocateDataPath(self):
        allocator = self.allocator
        clk_period = allocator.parentHls.clk_period
        fsm = self.fsm

        # instantiate logic in the states
        fsmEndClk_i = int(max(max(*node.scheduledIn, *node.scheduledOut, 0) for node in fsm.states[-1]) // clk_period)
        stateCons = self.connections
        for nodes in self.fsm.states:
            con = ConnectionsOfStage()
            stateCons.append(con)
            for node in nodes:
                rtl = allocator._instantiate(node, con.signals)

                if isinstance(node, HlsRead):
                    if not isinstance(node.src, (Signal, RtlSignal)):
                        con.inputs.append(node.src)
                    allocator._copy_sync(node.src, node, con.io_skipWhen, con.io_extraCond, con.signals)

                elif isinstance(node, HlsWrite):
                    con.stDependentDrives.append(rtl)
                    if not isinstance(node.src, (Signal, RtlSignal)):
                        con.outputs.append(node.dst)
                    allocator._copy_sync(node.dst, node, con.io_skipWhen, con.io_extraCond, con.signals)

            # mark value in register as persisten until the end of fsm
            for s in con.signals:
                s: TimeIndependentRtlResource
                if not s.persistenceRanges:
                    # val for the first clock behind this is int the register and the rest is persistent
                    nextClkI = start_clk(s.timeOffset, clk_period) + 2
                    if nextClkI <= fsmEndClk_i:
                        s.persistenceRanges.append((nextClkI, fsmEndClk_i))

    def allocateSync(self):
        """
        :note: This function does not perform efficient register allocations.
            Instead each value is store in idividual register.
            The register is created when value (TimeIndependentRtlResource) is first used from other state/clock cycle.
            
        """
        fsm = self.fsm
        assert fsm.states, fsm
        allocator = self.allocator
        clk_period = allocator.parentHls.clk_period
        self._initNopValsOfIo()
        
        st = allocator._reg(f"fsm_st_{fsm.intf._name}", Bits(log2ceil(len(fsm.states)), signed=False), def_val=0)
        
        fsmBeginClk_i = int(min(min(node.scheduledIn) for node in fsm.states[0]) // clk_period)
        # instantiate control of the FSM
        seenRegs: Set[TimeIndependentRtlResource] = set()
        stateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
        for stI, con in enumerate(self.connections):
            for s in con.signals:
                s: TimeIndependentRtlResource
                # if the value has a register at the end of this stage
                v = s.checkIfExistsInClockCycle(fsmBeginClk_i + stI + 1)
                if v is not None and v.is_rlt_register() and not v in seenRegs:
                    con.stDependentDrives.append(v.data.next.drivers[0])
                    seenRegs.add(v)

            unconditionalTransSeen = False
            inStateTrans: List[Tuple[RtlSignal, List[HdlStatement]]] = []
            sync = allocator._makeSyncNode(con)
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
