from functools import lru_cache
from math import log2
from pathlib import Path
from typing import Dict, Optional, Union

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform
from hwtHls.ssa.instr import OP_ASSIGN

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
    OP_ASSIGN,
}
_OPS_T_GROWING_CONST = {
    AllOps.NOT,
    AllOps.XOR,
    AllOps.AND,
    AllOps.OR,
    *_OPS_T_ZERO_LATENCY,
    ResourceFF,
}


class VirtualHlsPlatform(DefaultHlsPlatform):
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]=None):
        super(VirtualHlsPlatform, self).__init__(debugDir=debugDir)

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
            ResourceFF: 1.2e-9,
            OP_ASSIGN: 0,
        }

    @lru_cache()
    def get_op_realization(self, op: OpDefinition, bit_width: int,
                           input_cnt: int, clkPeriod: float) -> OpRealizationMeta:
        base_delay = self._OP_DELAYS[op]
        if op in _OPS_T_GROWING_CONST:
            inputWireDelay = base_delay

        elif op in _OPS_T_GROWING_LIN:
            inputWireDelay = base_delay * log2(bit_width)

        elif op in _OPS_T_GROWING_EXP:
            inputWireDelay = base_delay * bit_width

        elif op == AllOps.TERNARY:
            inputWireDelay = base_delay * log2(bit_width * input_cnt)

        else:
            raise NotImplementedError(op)

        return OpRealizationMeta(inputWireDelay=inputWireDelay)

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, 1, 1, realTimeClkPeriod).inputWireDelay // schedulerResolution)
