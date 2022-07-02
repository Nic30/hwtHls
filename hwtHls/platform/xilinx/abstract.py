from functools import lru_cache
from pathlib import Path
from typing import Dict, Callable, Tuple, Optional, Union

from hwt.hdl.operatorDefs import OpDefinition
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.platform.virtual import _OPS_T_ZERO_LATENCY


class AbstractXilinxPlatform(DefaultHlsPlatform):
    """
    :ivar _OP_DELAYS: dict operator -> function (number of args, bitwidth input, min latency in cycles, maximum_time_budget) -> delay in seconds

    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=None):
        super(AbstractXilinxPlatform, self).__init__(debugDir=debugDir)
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
        (outputClkTickOffset, inputWireDelay) = self._OP_DELAYS[op](input_cnt, bit_width, 0, clkPeriod)
        return OpRealizationMeta(inputWireDelay=float(inputWireDelay), outputClkTickOffset=float(outputClkTickOffset))

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, 1, 1, realTimeClkPeriod).inputWireDelay // schedulerResolution)
