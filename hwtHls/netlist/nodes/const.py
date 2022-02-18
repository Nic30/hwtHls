from hwt.hdl.value import HValue
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsNetNodeConst(HlsNetNode):
    """
    Wrapper around constant value for HLS sybsystem
    """

    def __init__(self, parentHls: "HlsPipeline", val: HValue):
        self.val = val
        HlsNetNode.__init__(self, parentHls, None)
        self._add_output(val._dtype)

    def get(self, time: float):
        return self.val

    def allocateRtlInstance(self, allocator: "AllocatorArchitecturalElement") -> TimeIndependentRtlResource:
        s = self.val
        t = TimeIndependentRtlResource.INVARIANT_TIME
        return TimeIndependentRtlResource(s, t, allocator)

    def resolve_realization(self):
        self.latency_pre = ()
        self.latency_post = (0.0,)
        self.asap_start = (0.0,)
        self.asap_end = (0.0,)

    def __repr__(self, minify=False):
        if minify:
            return repr(self.val)
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.val}>"

