
from hwtHls.architecture.archElementFsm import ArchElementFsm
from hwtHls.architecture.archElementPipeline import ArchElementPipeline
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.architecture.transformation.rtlNetlistPass import RtlNetlistPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.platform.fileUtils import OutputStreamGetter


class RtlNetlistPassDumpStreamNodes(RtlNetlistPass):
    """
    Dump text representations of stream synchronization nodes in architecture for debugging purposes.
    """
    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            for elem_i, elm in enumerate(netlist.allocator._archElements):
                out.write(f"########## {elem_i:d} {elm.__class__.__name__:s} {elm.namePrefix} ##########\n")
                # nodes = [n._id for n in elm.allNodes]
                # nodes.sort()
                # out.write(f" nodes={nodes}\n")
                if isinstance(elm, (ArchElementFsm, ArchElementPipeline)):
                    elm: ArchElementPipeline
                    stages = elm.stages if isinstance(elm, ArchElementPipeline) else elm.fsm.states
                    for st_i, (stCon, stNodes) in enumerate(zip(elm.connections, stages)):
                        stCon: ConnectionsOfStage
                        if not stNodes:
                            continue
                        out.write(f" ########## st {st_i:d} ##########\n")
                        nodes = [n._id for n in stNodes]
                        nodes.sort()
                        out.write(f"   nodes={nodes}\n")
                        if isinstance(elm, ArchElementFsm):
                            elm: ArchElementFsm
                            out.write("   transitionTable:\n")
                            for dstStI, cond in sorted(elm.transitionTable[st_i].items(), key=lambda tr: (isinstance(tr[1], int), tr[0])):
                                out.write(f"      {elm.stateEncoding[dstStI]} when {cond}\n")
                            out.write("\n")
                            
                        if stCon.sync_node is not None:
                            out.write(repr(stCon.sync_node))
                            out.write("\n")
                else:
                    raise NotImplementedError(elm)
        finally:
            if doClose:
                out.close()
