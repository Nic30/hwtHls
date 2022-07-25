
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.fileUtils import OutputStreamGetter


class RtlNetlistPassDumpStreamNodes(RtlNetlistPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            for elem_i, elm in enumerate(netlist.allocator._archElements):
                out.write(f"########## {elm.__class__.__name__:s} {elem_i:d} ##########\n")
                if isinstance(elm, (ArchElementFsm, ArchElementPipeline)):
                    elm: ArchElementPipeline
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
