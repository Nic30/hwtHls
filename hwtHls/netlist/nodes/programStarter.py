from hwt.hdl.types.defs import BIT
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.explicitSync import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.read import HlsNetNodeRead


class HlsProgramStarter(HlsNetNodeRead):
    """
    A node with produces just a single sync token to start the program after reset.
    """

    def __init__(self, netlist:HlsNetlistCtx, name:str=None):
        HlsNetNodeRead.__init__(self, netlist, None, BIT, name=name, addPortDataOut=False)
        self._portDataOut = None

    def getStartEnPort(self):
        return self.getValidNB()

    @override
    def resolveRealization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    @override
    def rtlAlloc(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        assert not self._isRtlAllocated, self
        assert self._portDataOut is None, self
        assert self._associatedReadSync is None, self
        assert self._ready is None, self
        assert self._readyNB is None, self
        assert self._valid is None, self
        assert self.skipWhen is None, self
        # assert self.extraCond is not None, self

        name = self.name
        starterReg = allocator._reg(name if name else f"{allocator.namePrefix:s}programStarter{self._id:d}", def_val=1)
        starterReg.hidden = False

        # sync added later
        starterReg(0)
        opOut = self._validNB
        assert opOut is not None, (self, "If it is not used this node should have been removed")
        assert self._valid is None
        res = allocator.rtlRegisterOutputRtlSignal(opOut, starterReg, True, False, True)
        self._isRtlAllocated = True
        return res

    def __repr__(self):
        return f"<{self.__class__.__name__:s} {self._id:d}>"
