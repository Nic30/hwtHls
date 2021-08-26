from functools import lru_cache

from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwtHls.allocator.allocator import HlsAllocator
from math import log2
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scheduler.list_schedueling import ListSchedueler
from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwt.hdl.operator import Operator
from typing import Dict

_OPS_T_GROWING_EXP = {
    AllOps.DIV,
    AllOps.POW,
    AllOps.MUL,
    AllOps.MOD,
}

_OPS_T_GROWING_LIN = {
    AllOps.ADD,
    AllOps.SUB,
    AllOps.MINUS_UNARY,
    AllOps.EQ,
    AllOps.NE,
    AllOps.GT,
    AllOps.GE,
    AllOps.LT,
    AllOps.LE,
}

_OPS_T_ZERO_LATENCY = {
    AllOps.INDEX,
    AllOps.CONCAT,
    AllOps.BitsAsSigned,
    AllOps.BitsAsVec,
    AllOps.BitsAsUnsigned,
}
_OPS_T_GROWING_CONST = {
    AllOps.NOT,
    AllOps.XOR,
    AllOps.AND,
    AllOps.OR,
    *_OPS_T_ZERO_LATENCY,
}


class VirtualHlsPlatform(DummyPlatform):
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """

    def __init__(self, allocator=HlsAllocator, scheduler=ListSchedueler):
        super(VirtualHlsPlatform, self).__init__()
        self.allocator = allocator
        self.scheduler = scheduler  # HlsScheduler #ForceDirectedScheduler

        # operator: seconds to perform
        self._OP_DELAYS: Dict[Operator, float] = {
            # exponentially growing with bit width
            AllOps.DIV: 0.9e-9,
            AllOps.POW: 0.6e-9,
            AllOps.MUL: 0.6e-9,
            AllOps.MOD: 0.9e-9,

            # nearly constant with bit width
            AllOps.NOT: 1.2e-9,
            AllOps.XOR: 1.2e-9,
            AllOps.AND: 1.2e-9,
            AllOps.OR: 1.2e-9,

            # nearly linear with bit width
            AllOps.ADD: 1.5e-9,
            AllOps.SUB: 1.5e-9,
            AllOps.MINUS_UNARY: 1.5e-9,

            AllOps.EQ: 1.5e-9,
            AllOps.NE: 1.5e-9,
            AllOps.GT: 1.5e-9,
            AllOps.GE: 1.5e-9,
            AllOps.LT: 1.5e-9,
            AllOps.LE: 1.5e-9,

            # depends on number of inputs and bit width
            AllOps.TERNARY: 0.8e-9,
            # constant
            AllOps.INDEX: 0,
            AllOps.CONCAT: 0,
            AllOps.BitsAsSigned: 0,
            AllOps.BitsAsVec: 0,
            AllOps.BitsAsUnsigned: 0,
        }

    @lru_cache()
    def get_op_realization(self, op: OpDefinition, bit_width: int,
                           input_cnt: int, clk_period: float) -> OpRealizationMeta:
        base_delay = self._OP_DELAYS[op]
        if op in _OPS_T_GROWING_CONST:
            latency_pre = base_delay

        elif op in _OPS_T_GROWING_LIN:
            latency_pre = base_delay * log2(bit_width)

        elif op in _OPS_T_GROWING_EXP:
            latency_pre = base_delay * bit_width

        elif op == AllOps.TERNARY:
            latency_pre = base_delay * log2(bit_width * input_cnt)

        else:
            raise NotImplementedError(op)

        return OpRealizationMeta(latency_pre=latency_pre)

