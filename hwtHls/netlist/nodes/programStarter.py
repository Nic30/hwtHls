from hwt.hdl.types.defs import BIT
from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.netlist.nodes.io import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.node import HlsNetNode


class HlsProgramStarter(HlsNetNode):
    """
    A node with produces just a single sync token to start the program after reset.
    """

    def __init__(self, parentHls:"HlsPipeline", name:str=None):
        HlsNetNode.__init__(self, parentHls, name=name)
        self._add_output(BIT)

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocateRtlInstance(self, allocator: "AllocatorArchitecturalElement") -> TimeIndependentRtlResource:
        op_out = self._outputs[0]

        try:
            return allocator.netNodeToRtl[op_out]
        except KeyError:
            pass

        name = self.name
        starter_reg = allocator._reg(name if name else f"{allocator.namePrefix:s}program_starter", def_val=1)

        # sync added later
        starter_reg(0)

        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + self.hls.scheduler.epsilon
        status_reg_s = TimeIndependentRtlResource(starter_reg, t, allocator)
        allocator.netNodeToRtl[op_out] = status_reg_s

        return status_reg_s

    def __repr__(self):
        return f"<{self.__class__.__name__:s}>"
