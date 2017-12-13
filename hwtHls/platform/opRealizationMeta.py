

class OpRealizationMeta():
    def __init__(self, latency_pre=0.0, latency_post=0.0,
                 cycles_latency=0.0, cycles_delay=0.0):
        self.latency_pre = latency_pre
        self.latency_post = latency_post
        self.cycles_latency = cycles_latency
        self.cycles_delay = cycles_delay


EMPTY_OP_REALIZATION = OpRealizationMeta()
UNSPECIFIED_OP_REALIZATION = OpRealizationMeta(
    latency_pre=None, latency_post=None,
    cycles_latency=None, cycles_delay=None)
