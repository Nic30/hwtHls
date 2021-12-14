from functools import lru_cache
from math import log2
from pathlib import Path
from typing import Dict, Union, Optional, List

from hwt.hdl.operator import Operator
from hwt.hdl.operatorDefs import AllOps, OpDefinition
from hwt.synthesizer.dummyPlatform import DummyPlatform
from hwtHls.allocator.allocator import HlsAllocator
from hwtHls.llvm.fromLlvm import SsaPassFromLlvm
from hwtHls.llvm.toLlvmPy import SsaPassToLlvm
from hwtHls.netlist.toGraphwiz import HlsNetlistPassDumpToDot
from hwtHls.netlist.toTimeline import RtlNetlistPassShowTimeline
from hwtHls.netlist.transformations.hlsNetlistPass import HlsNetlistPass
from hwtHls.netlist.transformations.mergeExplicitSync import HlsNetlistPassMergeExplicitSync
from hwtHls.platform.opRealizationMeta import OpRealizationMeta
from hwtHls.scheduler.list_schedueling import ListSchedueler
from hwtHls.ssa.analysis.consystencyCheck import SsaPassConsystencyCheck
from hwtHls.ssa.instr import OP_ASSIGN
from hwtHls.ssa.transformation.extractPartDrivers import SsaPassExtractPartDrivers
from hwtHls.ssa.transformation.removeTrivialBlocks import SsaPassRemoveTrivialBlocks
from hwtHls.ssa.transformation.runLlvmOpt import SsaPassRunLlvmOpt
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.toGraphwiz import SsaPassDumpToDot
from hwtHls.ssa.translation.toLl import SsaPassDumpToLl
from hwtHls.ssa.transformation.expandControlSelfLoops import SsaPassExpandControlSelfloops
from hwtHls.netlist.dumpStreamNodes import RtlNetlistPassDumpStreamNodes
from hwtHls.ssa.analysis.dumpPipelines import SsaPassDumpPipelines

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
}

DEFAULT_SSA_PASSES = [
    SsaPassConsystencyCheck(),
    SsaPassExtractPartDrivers(),
    SsaPassToLlvm(),
    SsaPassRunLlvmOpt(),
    SsaPassFromLlvm(),
    SsaPassConsystencyCheck(),
]
DEFAULT_HLSNETLIST_PASSES = [
    HlsNetlistPassMergeExplicitSync(),
]
DEFAULT_RTLNETLIST_PASSES = [
]


def makeDebugPasses(debug_file_directory: Union[str, Path]):
    """
    Adds passes which are dumping the intermediate results during the compilation.

    Example of use:

    .. code-block::

        print(to_rtl_str(u, target_platform=VirtualHlsPlatform(**make_debug_passes("tmp"))))

    """
    debug_file_directory = Path(debug_file_directory)
    return {
        "ssa_passes": [
            SsaPassConsystencyCheck(),
            SsaPassExtractPartDrivers(),
            #SsaPassDumpToDot(debug_file_directory / "top0.dot"),
            SsaPassToLlvm(),
            #SsaPassDumpToLl(open(debug_file_directory / "top1.ll", "w"), close=True),
            SsaPassRunLlvmOpt(),
            SsaPassDumpToLl(open(debug_file_directory / "top2.ll", "w"), close=True),
            SsaPassFromLlvm(),
            SsaPassDumpToDot(debug_file_directory / "top3.dot"),
            SsaPassDumpPipelines(open(debug_file_directory / "top.pipeline.txt", "w"), close=True),
            SsaPassConsystencyCheck(),
        ],
        "hlsnetlist_passes":[
            #HlsNetlistPassDumpToDot(debug_file_directory / "top_p0.dot"),
            HlsNetlistPassMergeExplicitSync(),
            #HlsNetlistPassDumpToDot(debug_file_directory / "top_p1.dot"),
        ],
        "rtlnetlist_passes":[
            RtlNetlistPassShowTimeline(debug_file_directory / "top.schedule.html"),
            RtlNetlistPassDumpStreamNodes(open(debug_file_directory / "top.sync.txt", "w"), close=True)
        ],

    }


class VirtualHlsPlatform(DummyPlatform):
    """
    Platform with informations about target platform
    and configuration of HLS

    :note: latencies like in average 28nm FPGA
    """

    def __init__(self, allocator=HlsAllocator, scheduler=ListSchedueler,
                 ssa_passes:Optional[List[SsaPass]]=DEFAULT_SSA_PASSES,
                 hlsnetlist_passes: Optional[List[HlsNetlistPass]]=DEFAULT_HLSNETLIST_PASSES,
                 rtlnetlist_passes=DEFAULT_RTLNETLIST_PASSES,
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
            OP_ASSIGN: 0,
        }
        self.ssa_passes = ssa_passes
        self.hlsnetlist_passes = hlsnetlist_passes
        self.rtlnetlist_passes = rtlnetlist_passes

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

