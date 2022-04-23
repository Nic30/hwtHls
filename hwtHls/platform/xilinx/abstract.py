from functools import lru_cache
from typing import Dict, Callable, Tuple

from hwt.hdl.operatorDefs import OpDefinition
from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.allocator.allocator import HlsAllocator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.virtual import _OPS_T_ZERO_LATENCY, DEFAULT_SSA_PASSES, \
    DEFAULT_HLSNETLIST_PASSES, DEFAULT_RTLNETLIST_PASSES
from hwtHls.scheduler.scheduler import HlsScheduler
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF


class AbstractXilinxPlatform(DummyPlatform):
    """
    :ivar _OP_DELAYS: dict operator -> function (number of args, bitwidth input, min latency in cycles, maximum_time_budget) -> delay in seconds

    """

    def __init__(self, allocator=HlsAllocator,
                 scheduler=HlsScheduler,
                 ssaPasses=DEFAULT_SSA_PASSES,
                 hlsNetlistPasses=DEFAULT_HLSNETLIST_PASSES,
                 rtlNetlistPasses=DEFAULT_RTLNETLIST_PASSES
                 ):
        super(AbstractXilinxPlatform, self).__init__()
        self.allocator = allocator
        self.scheduler = scheduler  # HlsScheduler #ForceDirectedScheduler
        self.ssaPasses = ssaPasses
        self.hlsNetlistPasses = hlsNetlistPasses
        self.rtlNetlistPasses = rtlNetlistPasses

        self._init_coefs()

    def _init_coefs(self):
        """
        set delay/area coefficients
        """
        raise NotImplementedError(
            "Override this in your implementation of platform")
        self._OP_DELAYS: Dict[str, Callable[[int, int, int, float], Tuple[int, float]]] = {}

    @lru_cache()
    def get_op_realization(self, op: OpDefinition, bit_width: int,
                           input_cnt: int, clkPeriod: float) -> OpRealizationMeta:
        if op in _OPS_T_ZERO_LATENCY:
            return OpRealizationMeta()
        (cycles_latency, latency_pre) = self._OP_DELAYS[op](bit_width, input_cnt, 0, clkPeriod)
        return OpRealizationMeta(latency_pre=float(latency_pre), cycles_latency=float(cycles_latency))

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, 1, 1, realTimeClkPeriod).latency_pre // schedulerResolution)
