from hwt.hdl.types.defs import BIT
from hwtHls.architecture.timeIndependentRtlResource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsProgramStarter(HlsNetNode):
    """
    A node with produces just a single sync token to start the program after reset.
    """

    def __init__(self, netlist:"HlsNetlistCtx", name:str=None):
        HlsNetNode.__init__(self, netlist, name=name)
        self._addOutput(BIT, "start")

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self, allocator: "ArchElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        name = self.name
        starterReg = allocator._reg(name if name else f"{allocator.namePrefix:s}programStarter{self._id}", def_val=1)

        # sync added later
        starterReg(0)

        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + self.netlist.scheduler.epsilon
        status_reg_s = TimeIndependentRtlResource(starterReg, t, allocator)
        allocator.netNodeToRtl[op_out] = status_reg_s

        return status_reg_s

    def __repr__(self):
        return f"<{self.__class__.__name__:s}>"
