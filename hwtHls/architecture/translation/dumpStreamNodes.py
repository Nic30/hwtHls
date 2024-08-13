
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.hlsAndRtlNetlistAnalysisPass import HlsAndRtlNetlistAnalysisPass
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.platform.fileUtils import OutputStreamGetter


class HlsAndRtlNetlistPassDumpStreamNodes(HlsAndRtlNetlistAnalysisPass):
    """
    Dump text representations of stream synchronization nodes in architecture for debugging purposes.
    """

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            for elem_i, elm in enumerate(netlist.nodes):
                elm: ArchElement
                out.write(f"########## {elem_i:d} {elm.__class__.__name__:s} {elm.name} ##########\n")
                if isinstance(elm, (ArchElementFsm, ArchElementPipeline)):
                    elm: ArchElementPipeline
                    stages = elm.stages if isinstance(elm, ArchElementPipeline) else elm.fsm.states
                    for st_i, (stCon, stNodes) in enumerate(zip(elm.connections, stages)):
                        stCon: ConnectionsOfStage
                        if not stNodes:
                            continue

                        if isinstance(elm, ArchElementFsm):
                            out.write(f" ########## st {elm.stateEncoding[st_i]:d} (clk {st_i:d}) ##########\n")
                        else:
                            out.write(f" ########## st {st_i:d} ##########\n")

                        nodes = [n._id for n in stNodes]
                        nodes.sort()
                        out.write(f"   nodes={nodes}\n")
                        if isinstance(elm, ArchElementFsm):
                            elm: ArchElementFsm
                            out.write("   transitionTable:\n")
                            for dstStI, cond in sorted(elm.transitionTable[st_i].items(), key=lambda tr: (isinstance(tr[1], int), tr[0])):
                                out.write(f"      {elm.stateEncoding[dstStI]} (clk {dstStI:d}) when {cond}\n")
                            out.write("\n")

                        if stCon.syncNode is not None:
                            out.write(repr(stCon.syncNode))
                            out.write("\n")
                elif isinstance(elm, ArchElementNoSync):
                    pass
                else:
                    raise NotImplementedError(elm)
        finally:
            if doClose:
                out.close()
