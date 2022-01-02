from io import StringIO
from hwtHls.netlist.transformations.rtlNetlistPass import RtlNetlistPass
from hwtHls.allocator.allocator import ConnectionsOfStage
from hwtHls.allocator.pipelineContainer import PipelineContainer
from hwtHls.allocator.fsmContainer import FsmContainer


class RtlNetlistPassDumpStreamNodes(RtlNetlistPass):

    def __init__(self, out: StringIO, close=False):
        self.out = out
        self.close = close

    def apply(self, hls: "HlsStreamProc", to_hw: "SsaSegmentToHwPipeline"):
        if to_hw.backward_edges:
            self.out.write(f"########## backedges ##########\n")
            for e in to_hw.backward_edges:
                self.out.write(repr(e))
                self.out.write("\n")

            self.out.write("\n")
        for elem_i, elm in enumerate(to_hw.hls.allocator._archElements):
            self.out.write(f"########## {elm.__class__.__name__:s} {elem_i:d} ##########\n")
            if isinstance(elm, (FsmContainer, PipelineContainer)):
                elm: PipelineContainer
                for st_i, st in enumerate(elm.connections):
                    st: ConnectionsOfStage
                    self.out.write(f" ########## st {st_i:d} ##########\n")
                    if st.sync_node is not None:
                        self.out.write(repr(st.sync_node))
                        self.out.write("\n")
            else:
                raise NotImplementedError(elm)
                
        if self.close:
            self.out.close()
