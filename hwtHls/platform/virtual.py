from functools import lru_cache
from math import log2
from pathlib import Path
from typing import Dict, Optional, Union, Set

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform, DebugId, HlsDebugBundle
from hwtHls.ssa.instr import OP_ASSIGN
from hwtHls.code import OP_ASHR, OP_SHL, OP_LSHR, OP_CTLZ, OP_CTPOP, OP_CTTZ,\
    OP_BITREVERSE, OP_FSHR, OP_FSHL

_OPS_T_GROWING_EXP = {
    HwtOps.UDIV,
    HwtOps.SDIV,
    HwtOps.POW,
    HwtOps.MUL,
    HwtOps.MOD,
}

_OPS_T_GROWING_LIN = {
    HwtOps.ADD,
    HwtOps.SUB,
    HwtOps.MINUS_UNARY,
    HwtOps.EQ,
    HwtOps.NE,
    HwtOps.UGT,
    HwtOps.UGE,
    HwtOps.ULT,
    HwtOps.ULE,
    HwtOps.SGT,
    HwtOps.SGE,
    HwtOps.SLT,
    HwtOps.SLE,
}
_OPS_T_GROWING_LOG = {
    OP_ASHR,
    OP_LSHR,
    OP_SHL,
    OP_CTLZ,
    OP_CTTZ,
    OP_CTPOP,
    OP_FSHL,
    OP_FSHR,
}

_OPS_T_ZERO_LATENCY = {
    HwtOps.INDEX,
    HwtOps.CONCAT,
    OP_BITREVERSE,
    OP_ASSIGN,
}
_OPS_T_GROWING_CONST = {
    HwtOps.NOT,
    HwtOps.XOR,
    HwtOps.AND,
    HwtOps.OR,
    *_OPS_T_ZERO_LATENCY,
    ResourceFF,
}


class VirtualHlsPlatform(DefaultHlsPlatform):
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]="tmp", debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT):
        super(VirtualHlsPlatform, self).__init__(debugDir=debugDir, debugFilter=debugFilter)

        # operator: seconds to perform
        self._OP_DELAYS: Dict[HOperatorNode, float] = {
            # exponentially growing with bit width
            HwtOps.UDIV: 0.9e-9,
            HwtOps.SDIV: 0.9e-9,
            HwtOps.POW: 0.6e-9,
            HwtOps.MUL: 0.6e-9,
            HwtOps.MOD: 0.9e-9,

            # nearly constant with bit width
            HwtOps.NOT: 1.2e-9,
            HwtOps.XOR: 1.2e-9,
            HwtOps.AND: 1.2e-9,
            HwtOps.OR: 1.2e-9,

            # nearly logarithmical with bit widht
            OP_ASHR: 1.2e-9,
            OP_LSHR: 1.2e-9,
            OP_SHL: 1.2e-9,
            OP_CTLZ: 1.2e-9,
            OP_CTTZ: 1.2e-9,
            OP_CTPOP: 1.2e-9,

            # nearly linear with bit width
            HwtOps.ADD: 1.5e-9,
            HwtOps.SUB: 1.5e-9,
            HwtOps.MINUS_UNARY: 1.5e-9,

            HwtOps.EQ: 1.5e-9,
            HwtOps.NE: 1.5e-9,
            HwtOps.UGT: 1.5e-9,
            HwtOps.UGE: 1.5e-9,
            HwtOps.ULT: 1.5e-9,
            HwtOps.ULE: 1.5e-9,

            HwtOps.SGT: 1.5e-9,
            HwtOps.SGE: 1.5e-9,
            HwtOps.SLT: 1.5e-9,
            HwtOps.SLE: 1.5e-9,

            # depends on number of inputs and bit width
            HwtOps.TERNARY: 0.8e-9,
            # constant
            HwtOps.INDEX: 0,
            HwtOps.CONCAT: 0,
            ResourceFF: 1.2e-9,
            OP_ASSIGN: 0,
        }

    @lru_cache()
    def get_op_realization(self, op: HOperatorDef, bit_width: int,
                           input_cnt: int, clkPeriod: float) -> OpRealizationMeta:
        base_delay = self._OP_DELAYS[op]
        if op in _OPS_T_GROWING_CONST:
            inputWireDelay = base_delay

        elif op in _OPS_T_GROWING_LOG:
            inputWireDelay = base_delay * log2(log2(bit_width))

        elif op in _OPS_T_GROWING_LIN:
            inputWireDelay = base_delay * log2(bit_width)

        elif op in _OPS_T_GROWING_EXP:
            inputWireDelay = base_delay * bit_width

        elif op == HwtOps.TERNARY:
            inputWireDelay = base_delay * log2(bit_width * input_cnt)

        else:
            raise NotImplementedError(op)

        return OpRealizationMeta(inputWireDelay=inputWireDelay)

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, 1, 1, realTimeClkPeriod).inputWireDelay // schedulerResolution)
