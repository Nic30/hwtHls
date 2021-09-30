

class OpRealizationMeta():
    """
    :ivar in_cycles_offset: number of cycles from component first cycle when the input is accepted
    :ivar latency_pre: minimal amount of time until next clock cycle
    :ivar latency_post: time required to stabilize output value after clock cycle
    :ivar cycles_latency: number of clock cycles required for data to reach output
    :ivar cycles_delay: number of cycles required until input can process other data
    """

    def __init__(self, cycles_in_offset=0, latency_pre=0.0, latency_post=0.0,
                 cycles_latency=0, cycles_delay=0):
        self.in_cycles_offset = cycles_in_offset
        self.latency_pre = latency_pre
        self.latency_post = latency_post
        self.cycles_latency = cycles_latency
        self.cycles_delay = cycles_delay


EMPTY_OP_REALIZATION = OpRealizationMeta()
UNSPECIFIED_OP_REALIZATION = OpRealizationMeta(
    latency_pre=None, latency_post=None,
    cycles_latency=None, cycles_delay=None)
