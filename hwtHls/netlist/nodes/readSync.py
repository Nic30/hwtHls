from hwt.hdl.types.defs import BIT
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.node import HlsNetNode

from hwt.pyUtils.typingFuture import override


class HlsNetNodeReadSync(HlsNetNode):
    """
    Hls plane to read a synchronization from an interface.
    e.g. signal "valid" for handshaked input, signal "ready" for handshaked output.

    :ivar _sig: RTL signal in HLS context used for HLS code description
    :ivar src: original interface from which read should be performed

    :ivar dependsOn: list of dependencies for scheduling composed of extraConds and skipWhen
    """

    def __init__(self, netlist: HlsNetlistCtx):
        HlsNetNode.__init__(self, netlist, None)
        self._addInput("io")
        self._addOutput(BIT, "ack")

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        """
        Instantiate read operation on RTL level
        """
        assert not self._isRtlAllocated
        raise AssertionError("This node is not intended for RTL and should be lowered to HlsNetNodeRead._validNB or HlsNetNodeWrite._readyNB")

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"

