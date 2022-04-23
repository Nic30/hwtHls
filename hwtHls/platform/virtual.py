from functools import lru_cache
from math import log2
from pathlib import Path
from typing import Dict, Union, Optional, List

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.allocator.allocator import HlsAllocator
from hwtHls.netlist.analysis.consystencyCheck import HlsNetlistPassConsystencyCheck
from hwtHls.netlist.transformation.aggregateBitwiseOpsPass import HlsNetlistPassAggregateBitwiseOps
from hwtHls.netlist.transformation.dce import HlsNetlistPassDCE
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformation.mergeExplicitSync import HlsNetlistPassMergeExplicitSync
from hwtHls.netlist.translation.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.netlist.translation.toGraphwiz import HlsNetlistPassDumpToDot
from hwtHls.netlist.translation.toTimeline import HlsNetlistPassShowTimeline
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scheduler.scheduler import HlsScheduler
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.analysis.dumpPipelines import SsaPassDumpPipelines
from hwtHls.ssa.instr import OP_ASSIGN
from hwtHls.ssa.transformation.axiStreamReadLowering.axiStreamReadLoweringPass import SsaPassAxiStreamReadLowering
from hwtHls.ssa.transformation.extractPartDrivers.extractPartDriversPass import SsaPassExtractPartDrivers
from hwtHls.ssa.transformation.runLlvmOpt import SsaPassRunLlvmOpt
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.fromLlvm import SsaPassFromLlvm
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.translation.toLlvm import SsaPassToLlvm
from hwtHls.netlist.translation.toTimelineArchLevel import HlsNetlistPassShowTimelineArchLevel
from hwt.serializer.resourceAnalyzer.resourceTypes import ResourceFF
from hwtHls.platform.fileUtils import outputFileGetter

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

DEFAULT_SSA_PASSES = [
    SsaPassConsystencyCheck(),
    SsaPassAxiStreamReadLowering(),
    SsaPassExtractPartDrivers(),
    SsaPassToLlvm(),
    SsaPassRunLlvmOpt(),
    SsaPassFromLlvm(),
    SsaPassConsystencyCheck(),
]
DEFAULT_HLSNETLIST_PASSES = [
    HlsNetlistPassDCE(),
    HlsNetlistPassMergeExplicitSync(),
    HlsNetlistPassAggregateBitwiseOps(),
]
DEFAULT_RTLNETLIST_PASSES = [
]


def makeDebugPasses(debug_file_directory: Union[str, Path], expandCompositeNodes=False):
    """
    Adds passes which are dumping the intermediate results during the compilation.

    Example of use:

    .. code-block::

        print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**makeDebugPasses("tmp"))))

    """
    debug_file_directory = Path(debug_file_directory)
    if not debug_file_directory.exists():
        debug_file_directory.mkdir()
    return {
        "ssaPasses": [
            SsaPassDumpToDot(outputFileGetter(debug_file_directory, ".0.dot"), extractPipeline=False),
            SsaPassConsystencyCheck(),
            SsaPassAxiStreamReadLowering(),
            SsaPassDumpToDot(outputFileGetter(debug_file_directory, ".1.dot"), extractPipeline=False),
            SsaPassExtractPartDrivers(),
            SsaPassDumpToDot(outputFileGetter(debug_file_directory, ".2.dot"), extractPipeline=False),

            SsaPassToLlvm(),
            SsaPassDumpToLl(outputFileGetter(debug_file_directory, ".3.ll")),
            SsaPassRunLlvmOpt(),
            SsaPassDumpToLl(outputFileGetter(debug_file_directory, ".4.ll")),
            SsaPassFromLlvm(),

            SsaPassDumpToDot(outputFileGetter(debug_file_directory, ".5.dot")),
            SsaPassDumpPipelines(outputFileGetter(debug_file_directory, ".6.pipeline.txt")),
            SsaPassConsystencyCheck(),
        ],
        "hlsNetlistPasses": [
            HlsNetlistPassConsystencyCheck(),
            HlsNetlistPassDCE(),
            # HlsNetlistPassDumpToDot(debug_file_directory / "top_p0.dot"),
            HlsNetlistPassMergeExplicitSync(),
            HlsNetlistPassAggregateBitwiseOps(),
            # HlsNetlistPassConsystencyCheck(),
            # HlsNetlistPassDumpToDot(debug_file_directory / "top_p1.dot"),
            HlsNetlistPassShowTimeline(outputFileGetter(debug_file_directory, ".7.schedule.html"),
                                       expandCompositeNodes=expandCompositeNodes),
        ],
        "rtlNetlistPasses":[
            RtlNetlistPassDumpStreamNodes(outputFileGetter(debug_file_directory, ".8.sync.txt")),
            HlsNetlistPassShowTimelineArchLevel(outputFileGetter(debug_file_directory, ".9.archschedule.html")),
        ],
    }


class VirtualHlsPlatform(DummyPlatform):
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """

    def __init__(self, allocator=HlsAllocator, scheduler=HlsScheduler,
                 ssaPasses:Optional[List[SsaPass]]=DEFAULT_SSA_PASSES,
                 hlsNetlistPasses: Optional[List[HlsNetlistPass]]=DEFAULT_HLSNETLIST_PASSES,
                 rtlNetlistPasses=DEFAULT_RTLNETLIST_PASSES,
            ):
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
            ResourceFF: 1.2e-9,
            OP_ASSIGN: 0,
        }
        self.ssaPasses = ssaPasses
        self.hlsNetlistPasses = hlsNetlistPasses
        self.rtlNetlistPasses = rtlNetlistPasses

    @lru_cache()
    def get_op_realization(self, op: OpDefinition, bit_width: int,
                           input_cnt: int, clkPeriod: float) -> OpRealizationMeta:
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

    @lru_cache()
    def get_ff_store_time(self, realTimeClkPeriod: float, schedulerResolution: float):
        return int(self.get_op_realization(ResourceFF, 1, 1, realTimeClkPeriod).latency_pre // schedulerResolution)
