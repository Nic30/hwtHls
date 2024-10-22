from functools import lru_cache
from pathlib import Path
from typing import Dict, Callable, Tuple, Optional, Union, Set, List

from hwt.hdl.operatorDefs import HOperatorDef, HwtOps
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwtHls.llvm.llvmIr import HFloatTmpConfig
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform, DebugId, HlsDebugBundle, \
    LlvmCliArgTuple
from hwtHls.platform.virtual import _OPS_T_ZERO_LATENCY


class AbstractXilinxPlatform(DefaultHlsPlatform):
    """
    Base class for HlsPlatform implementations for Xilinx FPGAs

    :ivar _OP_DELAYS: dict operator -> function (number of args, bitwidth input, min latency in cycles, maximum_time_budget) -> delay in seconds
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=HlsDebugBundle.DEFAULT_DEBUG_DIR,
                 debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                 llvmCliArgs:List[LlvmCliArgTuple]=[]):
        super(AbstractXilinxPlatform, self).__init__(debugDir=debugDir, debugFilter=debugFilter, llvmCliArgs=llvmCliArgs)
        self._init_coefs()

    def _init_coefs(self):
        """
        set delay/area coefficients
        """
        raise NotImplementedError(
            "Override this in your implementation of platform")
        self._OP_DELAYS: Dict[str, Callable[[int, int, int, float], Tuple[int, float]]] = {}

    @lru_cache()
    def get_op_realization(self, op: HOperatorDef, opSpecialization: Optional[HFloatTmpConfig], bit_width: int,
                           input_cnt: int, clkPeriod: float) -> OpRealizationMeta:
        if op in _OPS_T_ZERO_LATENCY:
            return OpRealizationMeta()
        (outputClkTickOffset, inputWireDelay) = self._OP_DELAYS[op](input_cnt, bit_width, 0, clkPeriod)
        if op is HwtOps.NOT:
            assert input_cnt == 1, input_cnt
            inputWireDelay = 0.0  # set to 0 because in FPGA invertor is inlined to successor/predecessor node
        return OpRealizationMeta(inputWireDelay=float(inputWireDelay), outputClkTickOffset=int(outputClkTickOffset))

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, None, 1, 1, realTimeClkPeriod).inputWireDelay // schedulerResolution)
