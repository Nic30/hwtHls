from functools import lru_cache
from math import log2
from pathlib import Path
from typing import Dict, Optional, Union, Set, List

from hwt.hdl.operator import HOperatorNode
from hwt.hdl.operatorDefs import HwtOps, HOperatorDef
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF, \
    ResourceRAM
from hwtHls.architecture.componentGenerators.componentGeneratorMemory import ComponentGeneratorMemory
from hwtHls.architecture.componentGenerators.countBits import ComponentGeneratorCTLZ, \
    ComponentGeneratorCTTZ, ComponentGeneratorCTPOP
from hwtHls.architecture.componentGenerators.ext import ComponentGeneratorZExt, ComponentGeneratorSExt
from hwtHls.architecture.componentGenerators.fsh import ComponentGeneratorFshl, \
    ComponentGeneratorFshr
from hwtHls.architecture.componentGenerators.icmpNeEq import ComponentGeneratorICMP_EQ_NE
from hwtHls.architecture.componentGenerators.indexConst import ComponentGeneratorOP_INDEX_CONST
from hwtHls.architecture.componentGenerators.mul_hl import ComponentGeneratorMUL_HL
from hwtHls.code import OP_ASHR, OP_SHL, OP_LSHR, OP_CTLZ, OP_CTPOP, OP_CTTZ, \
    OP_BITREVERSE, OP_FSHR, OP_FSHL, OP_ROL, OP_ROR
from hwtHls.llvm.llvmIr import TargetOpcode
from hwtHls.netlist.extraOps import OP_MUL_HL
from hwtHls.netlist.nodes.memoryAllocationMeta import MemoryAllocationMeta
from hwtHls.netlist.nodes.ops import OP_INDEX_CONST
from hwtHls.platform.debugBundleTypes import LlvmCliArgTuple
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.platform.platform import DefaultHlsPlatform, DebugId, HlsDebugBundle


_OPS_T_GROWING_EXP = {
    HwtOps.POW,
    HwtOps.MUL,
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
    OP_ROL,
    OP_ROR,
    OP_FSHL,
    OP_FSHR,
}

_OPS_T_ZERO_LATENCY = {
    HwtOps.INDEX,
    HwtOps.CONCAT,
    OP_BITREVERSE,
}

_OPS_T_GROWING_LOG_INPUT_CNT = {
    HwtOps.XOR,
    HwtOps.AND,
    HwtOps.OR,
}

_OPS_T_GROWING_CONST = {
    HwtOps.NOT,
    *_OPS_T_ZERO_LATENCY,
    ResourceFF,
    ResourceRAM,
}


class VirtualHlsPlatform(DefaultHlsPlatform):
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """

    def __init__(self, debugDir:Optional[Union[str, Path]]="tmp",
                 debugFilter: Optional[Set[DebugId]]=HlsDebugBundle.DEFAULT,
                 llvmCliArgs:List[LlvmCliArgTuple]=[]):
        super(VirtualHlsPlatform, self).__init__(debugDir=debugDir, debugFilter=debugFilter, llvmCliArgs=llvmCliArgs)

        # operator: seconds to perform
        self._OP_DELAYS: Dict[HOperatorNode, float] = {
            # exponentially growing with bit width
            HwtOps.POW: 0.6e-9,
            HwtOps.MUL: 0.6e-9,

            # nearly constant with bit width
            HwtOps.NOT: 0.0,  # set to 0 because in FPGA invertor is inlined to successor/predecessor node
            HwtOps.XOR: 1.2e-9,
            HwtOps.AND: 1.2e-9,
            HwtOps.OR: 1.2e-9,

            # nearly logarithmical with bit width
            OP_ASHR: 1.2e-9,
            OP_LSHR: 1.2e-9,
            OP_SHL: 1.2e-9,
            OP_ROL: 1.2e-9,
            OP_ROR: 1.2e-9,

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
            ResourceRAM: 1.2e-9,
            ResourceFF: 1.2e-9,
        }
        # AMD/Xilinx 7-series https://0x04.net/~mwk/xidocs/ug/xc7-ram.pdf
        # :note: depth X data width
        # :attention: must be sorted, the smallest depth first
        self._BRAM_GEOMETRIES = [
            (512, 36),
            (1024, 18),
            (2048, 9),
            (4096, 4),
            (8192, 2),
            (16384, 1),
        ]
        # # Altera/Intel stratix-v https://cdrdv2-public.intel.com/670815/stx5_51001-683258-670815.pdf
        # [
        #    # MLAB
        #    (32, 20),
        #    (64, 10),
        #     # M20K
        #    (512, 40), # emulated using dual port https://www.intel.com/content/www/us/en/programmable/quartushelp/current/index.htm#reference/glossary/def_m20k.htm
        #    (1024, 20), # emulated using dual port
        #    (2048, 10),
        #    (4096, 5),
        #    (8192, 2),
        #    (16384, 1),
        # ]

        # https://0x04.net/~mwk/xidocs/ug/ug479_7Series_DSP48E1.pdf
        # https://projectf.io/posts/multiplication-fpga-dsps/
        # Altera Cyclone V: 27 x 27 bit
        # Lattice iCE40UP (SB_MAC16): 16 x 16 bit
        # Lattice ECP5 (sysDSP): 18 x 18 bit
        # Xilinx 7 Series (DSP48E1): 25 × 18 bit
        # Xilinx Ultrascale+ (DSP48E2): 27 x 18 bit

        self._DSP_MUL_GEOMETRIES = [
            (25, 18),
        ]
        self._installComponentGenerators()

    def _installComponentGenerators(self):
        genNamePrefix = "gen_"
        _componentGenerators = self._componentGenerators
        _componentGenerators[MemoryAllocationMeta] = ComponentGeneratorMemory(self, genNamePrefix, "mem")
        _componentGenerators[TargetOpcode] = _componentGenerators[HwtOps.ZEXT] = ComponentGeneratorZExt(self, genNamePrefix, "zext")
        _componentGenerators[HwtOps.SEXT] = ComponentGeneratorSExt(self, genNamePrefix, "sext")
        _componentGenerators[HwtOps.EQ] = ComponentGeneratorICMP_EQ_NE(self, genNamePrefix, "eq", HwtOps.EQ)
        _componentGenerators[HwtOps.NE] = ComponentGeneratorICMP_EQ_NE(self, genNamePrefix, "ne", HwtOps.NE)
        _componentGenerators[OP_MUL_HL] = ComponentGeneratorMUL_HL(self, genNamePrefix, "mul_hl")
        _componentGenerators[TargetOpcode.G_CTLZ] = \
        _componentGenerators[TargetOpcode.G_CTLZ_ZERO_UNDEF] = \
        _componentGenerators[TargetOpcode.HWTFPGA_CTLZ] = \
        _componentGenerators[TargetOpcode.HWTFPGA_CTLZ_ZERO_UNDEF] = \
        _componentGenerators[OP_CTLZ] = ComponentGeneratorCTLZ(self, genNamePrefix, "ctlz")
        _componentGenerators[TargetOpcode.G_CTTZ] = \
        _componentGenerators[TargetOpcode.G_CTTZ_ZERO_UNDEF] = \
        _componentGenerators[TargetOpcode.HWTFPGA_CTTZ] = \
        _componentGenerators[TargetOpcode.HWTFPGA_CTTZ_ZERO_UNDEF] = \
        _componentGenerators[OP_CTTZ] = ComponentGeneratorCTTZ(self, genNamePrefix, "cttz")
        _componentGenerators[TargetOpcode.G_CTPOP] = \
        _componentGenerators[TargetOpcode.HWTFPGA_CTPOP] = \
        _componentGenerators[OP_CTPOP] = ComponentGeneratorCTPOP(self, genNamePrefix, "ctpop")
        _componentGenerators[OP_FSHL] = ComponentGeneratorFshl(self, genNamePrefix, "fshl")
        _componentGenerators[OP_FSHR] = ComponentGeneratorFshr(self, genNamePrefix, "fshr")
        _componentGenerators[OP_INDEX_CONST] = ComponentGeneratorOP_INDEX_CONST(self, genNamePrefix, "slice")

    @lru_cache()
    def get_op_realization(self, op: HOperatorDef, opSpecialization: "OpSpecialization_t", bit_width: int,
                           input_cnt: int, clkPeriod: float) -> OpRealizationMeta:
        if opSpecialization is not None:
            raise NotImplementedError(op, opSpecialization)

        try:
            base_delay = self._OP_DELAYS[op]
        except KeyError:
            raise NotImplementedError(op)

        if op in _OPS_T_GROWING_CONST:
            inputWireDelay = base_delay

        elif op in _OPS_T_GROWING_LOG_INPUT_CNT:
            inputWireDelay = base_delay * max(1, log2(log2(input_cnt)))

        elif op in _OPS_T_GROWING_LOG:
            inputWireDelay = base_delay * (1 if bit_width == 1 else max(1, log2(log2(bit_width))))

        elif op in _OPS_T_GROWING_LIN:
            inputWireDelay = base_delay * max(1, log2(bit_width))

        elif op in _OPS_T_GROWING_EXP:
            inputWireDelay = base_delay * bit_width

        elif op == HwtOps.TERNARY:
            inputWireDelay = base_delay * max(1, log2(bit_width * input_cnt))

        else:
            raise NotImplementedError(op)

        return OpRealizationMeta(inputWireDelay=inputWireDelay)

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, None, 1, 1, realTimeClkPeriod).inputWireDelay // schedulerResolution)

    def get_lut_inputs_max(self):
        """
        get maximum number of lut inputs
        """
        return 7

