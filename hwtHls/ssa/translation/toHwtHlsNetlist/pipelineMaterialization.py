from typing import List, Optional

from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.hlsStreamProc.statements import HlsStreamProcCodeBlock
from hwtHls.ssa.analysis.blockSyncType import SaaGetBlockSyncType
from hwtHls.ssa.analysis.liveness import ssa_liveness_edge_variables
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.translation.toHwtHlsNetlist.pipelineExtractor import PipelineExtractor
from hwtHls.ssa.translation.toHwtHlsNetlist.toHwtHlsNetlist import SsaToHwtHlsNetlist


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

   :ivar start: a block where the program excecution starts
   :ivar original_code: an original code for debug purposes
    """

    def __init__(self,
                 start: SsaBasicBlock,
                 original_code:Optional[HlsStreamProcCodeBlock]):
        self.start = start
        self.original_code = original_code
        self.is_scheduled = False

    def extract_pipeline(self):
        pe = PipelineExtractor()
        self.pipeline: List[SsaBasicBlock] = pe.collect_pipelines(self.start)
        self.edge_var_live = ssa_liveness_edge_variables(self.start)
        self.backward_edges = pe.backward_edges
        self.blockMeta = SaaGetBlockSyncType(self.start, self.backward_edges, self.edge_var_live).apply()

    def extract_hlsnetlist(self, parentUnit: Unit, freq: float):
        """
        :param parentUnit: an Unit instance where the circuit should be constructed
        :param freq: target clock frequency
        """
        self.hls: HlsPipeline = HlsPipeline(parentUnit, freq)
        toHlsNetlist = self.toHlsNetlist = SsaToHwtHlsNetlist(self.hls, self.start, self.backward_edges,
                                                              self.edge_var_live, self.blockMeta)
        # construct nodes for scheduling
        # first resolve how block will be synchronized so we do not need to backtrace later
        for block in self.pipeline:
            toHlsNetlist.to_hls_SsaBasicBlock_resolve_io_and_sync(block)

        # convert the code from the block to a netlist
        for block in self.pipeline:
            toHlsNetlist.to_hls_SsaBasicBlock(block)

        toHlsNetlist.finalize_out_of_pipeline_variables(self.pipeline)

        assert not self.hls.coherency_checked_io
        self.hls.coherency_checked_io = toHlsNetlist.io._out_of_hls_io

    def schedulerReset(self):
        self.is_scheduled = False

    def schedulerRun(self):
        self.is_scheduled = True
        self.hls.schedule()

    def construct_rtlnetlist(self):
        self.hls.synthesise()
