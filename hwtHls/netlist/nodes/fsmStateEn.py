from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsNetNodeFsmStateEn(HlsNetNode):
    """
    Node which provides enable signal for FSM state where it is placed and scheduled.
    (Also works for ArchElementPipeline where it holds vld for regs from previous stage, or 1 for the first stage.)
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        HlsNetNode.__init__(self, netlist, name=None)
        self._addOutput(BIT, "en")

    @override
    def rtlAlloc(self, allocator: "ArchElementFsm") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        o = self._outputs[0]
        c: ConnectionsOfStage = allocator.connections.getForTime(self.scheduledOut[0])
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
        self.scheduledIn = (0,)
        self.scheduledOut = (0,)
