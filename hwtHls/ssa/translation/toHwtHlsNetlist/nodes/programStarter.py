from hwtHls.allocator.time_independent_rtl_resource import TimeIndependentRtlResource
from hwtHls.clk_math import epsilon
from hwtHls.netlist.nodes.io import IO_COMB_REALIZATION
from hwtHls.netlist.nodes.ops import AbstractHlsOp
from hwtHls.allocator.connectionsOfStage import SignalsOfStages


class HlsProgramStarter(AbstractHlsOp):
    """
    A node with produces just a single sync token to start the program after reset.
    """

    def __init__(self, parentHls:"HlsPipeline", name:str=None):
        AbstractHlsOp.__init__(self, parentHls, name=name)
        self._add_output()

    def resolve_realization(self):
        self.assignRealization(IO_COMB_REALIZATION)

    def allocate_instance(self,
                          allocator: "HlsAllocator",
                          used_signals: SignalsOfStages
                          ) -> TimeIndependentRtlResource:
        op_out = self._outputs[0]

        try:
            return allocator.node2instance[op_out]
        except KeyError:
            pass

        name = self.name
        starter_reg = allocator._reg(name if name else "program_starter", def_val=1)

        # sync added later
        starter_reg(0)

        # create RTL signal expression base on operator type
        t = self.scheduledOut[0] + epsilon
        status_reg_s = TimeIndependentRtlResource(starter_reg, t, allocator)
        allocator._registerSignal(op_out, status_reg_s, used_signals.getForTime(t))
        return status_reg_s

    def __repr__(self):
        return f"<{self.__class__.__name__:s}>"
