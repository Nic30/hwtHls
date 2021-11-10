from typing import List, Set, Tuple

from hwt.code import If
from hwt.synthesizer.unit import Unit
from hwtHls.hlsPipeline import HlsPipeline
from hwtHls.hlsStreamProc.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.hlsStreamProc.ssa.basicBlock import SsaBasicBlock
from hwtHls.hlsStreamProc.ssa.translation.toHwtHlsNetlist.toHwtHlsNetlist import SsaToHwtHlsNetlist
from hwtHls.netlist.toGraphwiz import HwtHlsNetlistToGraphwiz
from hwtHls.netlist.transformations.mergeExplicitSync import merge_explicit_sync
from hwtHls.netlist.toTimeline import HwtHlsNetlistToTimeline


class SsaSegmentToHwPipeline():
    """
    We know the variables which are crossing pipeline boundary
    from out_of_pipeline_edges and edge_var_live.
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


   :ivar parent: an Unit instance where the circuit should be constructed
   :ivar freq: target clock frequency
    """

    def __init__(self, parent: Unit, freq: float):
        self.parent = parent
        self.freq = freq

    def _construct_pipeline(self,
                            start: SsaBasicBlock,
                            pipeline: List[SsaBasicBlock],
                            out_of_pipeline_edges: Set[Tuple[SsaBasicBlock, SsaBasicBlock]],
                            edge_var_live: EdgeLivenessDict):
        """
        :param pipeline: list of SsaBasicBlocks (represents DAG if out_of_pipeline_edges are cut off) to build the pipeline from

        :param start: a block where the program excecution starts
        :param out_of_pipeline_edges: a set of connections between block where pipeline should be cut in order to prevent cycles
            the data channels for this type of connections are added in post processing and are not part of scheduling
        :param edge_var_live: dictionary of variables which are alive on a specific edge between blocks
        :attention: it is expected that the blocks in pipeline are sorted in topological order
            it is important that the outputs from previous block are seen before inputs from previous block
            otherwise the input is threated as an input of pipeline instead of connection between stages in pipeline
        """
        parent = self.parent
        freq = self.freq

        hls: HlsPipeline = HlsPipeline(parent, freq).__enter__()

        toHlsNetlist = SsaToHwtHlsNetlist(hls, start, out_of_pipeline_edges, edge_var_live)
        try:
            toHlsNetlist.io.init_out_of_hls_variables()
            # construct nodes for scheduling
            for block in pipeline:
                toHlsNetlist.to_hls_SsaBasicBlock(block)
            toHlsNetlist.io.finalize_out_of_pipeline_variable_outputs()
        finally:
            # recover from HlsPipeline temporary modification of hls.parentUnit
            hls.parentUnit._sig = hls._unit_sig

        assert not hls.coherency_checked_io
        hls.coherency_checked_io = toHlsNetlist.io._out_of_hls_io

        merge_explicit_sync(hls.nodes)

        # [debug]
        to_graphwiz = HwtHlsNetlistToGraphwiz("top")
        with open("top_p.dot", "w") as f:
            to_graphwiz.construct(hls.inputs + hls.nodes + hls.outputs)
            f.write(to_graphwiz.dumps())

        hls.synthesise()
        to_timeline = HwtHlsNetlistToTimeline(hls.clk_period)
        to_timeline.construct(hls.inputs + hls.nodes + hls.outputs)
        to_timeline.show()

        if toHlsNetlist.start_block_en is not None:
            # the start_block_en may not be pressent if the code is and infinite cycle
            start_init = parent._reg(f"{start.label}_init", def_val=1)
            toHlsNetlist.start_block_en.vld(start_init)
            toHlsNetlist.start_block_en.data(1)
            If(toHlsNetlist.start_block_en.rd,
               start_init(0),
            )

