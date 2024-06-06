from hwt.hdl.const import HConst
from hwt.hdl.types.array import HArray
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsNetNodeConst(HlsNetNode):
    """
    Wrapper around constant value for HLS subsystem
    """

    def __init__(self, netlist: "HlsNetlistCtx", val: HConst):
        self.val = val
        HlsNetNode.__init__(self, netlist, name=None)
        self._addOutput(val._dtype, "val")

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated
        o = self._outputs[0]
        s = self.val
        if isinstance(s._dtype, HArray):
            # wrap into const signal to prevent code duplication
            s = allocator._sig(self.name, s._dtype, def_val=s)
            s._const = True
        
        res = allocator.rtlRegisterOutputRtlSignal(o, s, False, False, False)
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

    def __repr__(self, minify=False):
        if minify:
            return repr(self.val)
        else:
            return f"<{self.__class__.__name__:s} {self._id:d} {self.val}>"

