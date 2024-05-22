from hwt.hdl.types.defs import BIT
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.node import HlsNetNode
from hwt.pyUtils.typingFuture import override


class HlsProgramStarter(HlsNetNode):
    """
    A node with produces just a single sync token to start the program after reset.
    """

    def __init__(self, netlist:HlsNetlistCtx, name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addOutput(BIT, "start")

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated, self
        op_out = self._outputs[0]
        name = self.name
        starterReg = allocator._reg(name if name else f"{allocator.name:s}programStarter{self._id:d}", def_val=1)
        starterReg.hidden = False

        # sync added later
        starterReg(0)

        res = allocator.rtlRegisterOutputRtlSignal(op_out, starterReg, True, False, True)
        self._isRtlAllocated = True
        return res

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"
