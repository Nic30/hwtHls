from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsNetNodeFsmStateEn(HlsNetNode):
    """
    Node which provides enable signal for FSM state where it is placed and scheduled.
    (Also works for ArchElementPipeline where it holds vld for regs from previous stage, or 1 for the first stage.)

    :see: `Synchronization flag names`_
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetNode.__init__(self, netlist, name=None)
        self._addOutput(BIT, "en")

    @override
    def rtlAlloc(self, allocator: "ArchElementFsm") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        o = self._outputs[0]
        c: "ConnectionsOfStage" = allocator.connections.getForTime(self.scheduledOut[0])
        res = allocator.rtlRegisterOutputRtlSignal(o, c.getRtlStageEnableSignal(), False, False, False)
        self._isRtlAllocated = True
        return res

    @override
    def resolveRealization(self):
        assert not self._inputs
        assert len(self._outputs) == 1
        self.inputWireDelay = ()
        self.inputClkTickOffset = ()
        self.outputWireDelay = (0,)
        self.outputClkTickOffset = (0,)


class HlsNetNodeStageAck(HlsNetNode):
    """
    :see: `Synchronization flag names`_
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetNode.__init__(self, netlist, name=None)
        self._addInput("ackIn")

    @override
    def rtlAlloc(self, allocator: "ArchElementFsm") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        c: "ConnectionsOfStage" = allocator.connections.getForTime(self.scheduledIn[0])
        ackOut = c.getRtlStageAckSignal()
        ackIn = allocator.rtlAllocHlsNetNodeInDriverIfExists(self._inputs[0])
        ackOut(ackIn.data)
        assert ackIn, self
        self._isRtlAllocated = True
        return []

    @override
    def resolveRealization(self):
        assert len(self._inputs) == 1
        assert not self._outputs
        self.inputWireDelay = (0,)
        self.inputClkTickOffset = (0,)
        self.outputWireDelay = ()
        self.outputClkTickOffset = ()

