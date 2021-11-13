from typing import List, Optional

from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.hlsStreamProc.ssa.analysis.liveness import ssa_liveness_edge_variables
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.pipelineExtractor import PipelineExtractor
from hwtHls.hlsStreamProc.statements import HlsStreamProcCodeBlock
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.toHwtHlsNetlist import SsaToHwtHlsNetlist


class SsaSegmentToHwPipeline():
    """
    We know the variables which are crossing pipeline boundary
    from backward_edges and edge_var_live.
    These variables usually appear because of cycle which means
    that there could exists a code section which uses the value from a previous cycle iterration
    and a section which uses a newly generate value.
    This means that a single variable may appear in multiple versions even if it is written only once.
    The cycle may be entered only on a single place (header, because of structured programing).
    However the cycle may be entered from a multiple places and exited to multiple places.
    Which means that the value of variables alive on such a transitions can potentially
    come from multiple places.
    We can potentially instantiate buffers on every path. This however leads to resource wasting.
    Instead we want to output the variable value as soon as we are sure that variable will be consummed.
    This means that we need to walk the blocks instruction by instruction and resolve where the value
    from a previous cycle should be used and where new value may be mixed in or used exclusively.
    On each place where multiple values may appear due to branching we need to add multiplexer
    and use it in following expressions.

   :ivar parentUnit: an Unit instance where the circuit should be constructed
   :ivar freq: target clock frequency
   :ivar start: a block where the program excecution starts
   :ivar original_code: an original code for debug purposes
    """

    def __init__(self,
                 parentUnit: Unit,
                 freq: float,
                 start: SsaBasicBlock,
                 original_code:Optional[HlsStreamProcCodeBlock]):
        self.start = start
        self.parentUnit = parentUnit
        self.freq = freq
        self.original_code = original_code

    def extract_pipeline(self):
        pe = PipelineExtractor()
        pipeline: List[SsaBasicBlock] = []
        for comp in pe.collect_pipelines(self.start):
            pipeline.extend(comp)
        self.pipeline = pipeline
        self.edge_var_live = ssa_liveness_edge_variables(self.start)
        self.backward_edges = pe.backward_edges

    def extract_hlsnetlist(self):
        self.hls: HlsPipeline = HlsPipeline(self.parentUnit, self.freq)
        hls = self.hls
        self.toHlsNetlist = SsaToHwtHlsNetlist(hls, self.start, self.backward_edges, self.edge_var_live)
        toHlsNetlist = self.toHlsNetlist
        toHlsNetlist.io.init_out_of_hls_variables()
        # construct nodes for scheduling
        for block in self.pipeline:
            toHlsNetlist.to_hls_SsaBasicBlock(block)
        toHlsNetlist.io.finalize_out_of_pipeline_variable_outputs()

        assert not hls.coherency_checked_io
        hls.coherency_checked_io = toHlsNetlist.io._out_of_hls_io

    def construct_rtlnetlist(self):
        hls = self.hls
        hls.schedule()
        hls.synthesise()
