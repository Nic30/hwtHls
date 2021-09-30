from functools import lru_cache
from typing import Dict, Callable, Tuple

from hwt.hdl.operatorDefs import OpDefinition
from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.allocator.allocator import HlsAllocator
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scheduler.list_schedueling import ListSchedueler
from hwtHls.platform.virtual import _OPS_T_ZERO_LATENCY


class AbstractXilinxPlatform(DummyPlatform):
    """
    :ivar _OP_DELAYS: dict operator -> function (number of args, bitwidth input, min latency in cycles, maximum_time_budget) -> delay in seconds

    """

    def __init__(self, allocator=HlsAllocator, scheduler=ListSchedueler):
        super(AbstractXilinxPlatform, self).__init__()
        self.allocator = allocator
        self.scheduler = scheduler  # HlsScheduler #ForceDirectedScheduler

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
                           input_cnt: int, clk_period: float) -> OpRealizationMeta:
        if op in _OPS_T_ZERO_LATENCY:
            return OpRealizationMeta()
        (cycles_latency, latency_pre) = self._OP_DELAYS[op](bit_width, input_cnt, 0, clk_period)
        return OpRealizationMeta(latency_pre=float(latency_pre), cycles_latency=float(cycles_latency))

