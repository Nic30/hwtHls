from hwt.hdl.types.array import HArray
from hwt.hdl.value import HValue
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource, INVARIANT_TIME
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsNetNodeConst(HlsNetNode):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, netlist: "HlsNetlistCtx", val: HValue):
        self.val = val
        HlsNetNode.__init__(self, netlist, name=None)
        self._addOutput(val._dtype, "val")

    def get(self, time: float):
        return self.val

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        s = self.val
        if isinstance(s._dtype, HArray):
            # wrap into const signal to prevent code duplication
            s = allocator._sig(self.name, s._dtype, def_val=s)
            s._const = True

        return TimeIndependentRtlResource(s, INVARIANT_TIME, allocator, False)

    def resolveRealization(self):
        assert not self._inputs
        assert len(self._outputs) == 1
        self.inputWireDelay = ()
        self.inputClkTickOffset = ()
        self.outputWireDelay = (0,)
        self.outputClkTickOffset = (0,)
        self.scheduledIn = (0,)
        self.scheduledOut = (0,)

    def __repr__(self, minify=False):
        if minify:
            return repr(self.val)
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.val}>"

