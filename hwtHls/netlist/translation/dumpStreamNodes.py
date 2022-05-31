
from hwtHls.netlist.allocator.connectionsOfStage import ConnectionsOfStage
from hwtHls.netlist.allocator.fsmContainer import AllocatorFsmContainer
from hwtHls.netlist.allocator.pipelineContainer import AllocatorPipelineContainer
from hwtHls.netlist.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.netlist.context import HlsNetlistCtx


class RtlNetlistPassDumpStreamNodes(RtlNetlistPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsStreamProc", netlist: HlsNetlistCtx):
        out, doClose = self.outStreamGetter(netlist.parentUnit._getDefaultName())
        try:
            #if to_hw.backward_edges:
            #    out.write(f"########## backedges ##########\n")
            #    for e in to_hw.backward_edges:
            #        out.write(repr(e))
            #        out.write("\n")
            #
            #    out.write("\n")

            for elem_i, elm in enumerate(netlist.allocator._archElements):
                out.write(f"########## {elm.__class__.__name__:s} {elem_i:d} ##########\n")
                if isinstance(elm, (AllocatorFsmContainer, AllocatorPipelineContainer)):
                    elm: AllocatorPipelineContainer
                    for st_i, st in enumerate(elm.connections):
                        st: ConnectionsOfStage
                        out.write(f" ########## st {st_i:d} ##########\n")
                        if st.sync_node is not None:
                            out.write(repr(st.sync_node))
                            out.write("\n")
                else:
                    raise NotImplementedError(elm)
        finally: 
            if doClose:
                out.close()
