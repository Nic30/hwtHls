
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.hlsAndRtlNetlistAnalysisPass import HlsAndRtlNetlistAnalysisPass
from hwtHls.architecture.connectionsOfStage import ConnectionsOfStage
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.archElementFsm import ArchElementFsm
from hwtHls.netlist.nodes.archElementNoImplicitSync import ArchElementNoImplicitSync
from hwtHls.netlist.nodes.archElementPipeline import ArchElementPipeline
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.architecture.analysis.fsmStateEncoding import HlsAndRtlNetlistAnalysisPassFsmStateEncoding
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class HlsAndRtlNetlistPassDumpStreamNodes(HlsAndRtlNetlistAnalysisPass):
    """
    Dump text representations of stream synchronization nodes in architecture for debugging purposes.
    """

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        stateEncodingA: HlsAndRtlNetlistAnalysisPassFsmStateEncoding = netlist.getAnalysisIfAvailable(HlsAndRtlNetlistAnalysisPassFsmStateEncoding)
        out, doClose = self.outStreamGetter(netlist.label)
        try:
            for elem_i, elm in enumerate(netlist.subNodes):
                elm: ArchElement
                out.write(f"########## {elem_i:d} {elm.__class__.__name__:s} {elm.name} ##########\n")
                if isinstance(elm, (ArchElementFsm, ArchElementPipeline)):
                    elm: ArchElementPipeline
                    stages = elm.stages
                    if stateEncodingA is None:
                        stateEncoding = None
                    else:
                        stateEncoding = stateEncodingA.stateEncoding.get(elm, None)
                    for clkI, (stCon, stNodes) in enumerate(zip(elm.connections, stages)):
                        stCon: ConnectionsOfStage
                        if not stNodes:
                            continue

                        if stateEncoding is not None and isinstance(elm, ArchElementFsm):
                            out.write(f" ########## st {stateEncoding[clkI]:d} (clk {clkI:d}) ##########\n")
                        else:
                            out.write(f" ########## clk {clkI:d} ##########\n")

                        nodes = sorted(stNodes, key=lambda n: n._id)
                        out.write(f"   nodes={[n._id for n in nodes]}\n")
                        if isinstance(elm, ArchElementFsm):
                            elm: ArchElementFsm
                            out.write("   transitionTable:\n")
                            nextStW = stCon.fsmStateWriteNode
                            if nextStW is None:
                                out.write(f"      <missing HlsNetNodeFsmStateWrite node>\n")
                            else:
                                nextStW: HlsNetNodeFsmStateWrite
                                for i, cond in zip(nextStW._inputs, nextStW.dependsOn):
                                    dstStI = nextStW.portToNextStateId[i]
                                    out.write(f"      {stateEncoding[dstStI]} (clk {dstStI:d}) when {cond}\n")
                            out.write("\n")

                        out.write("   inputs (io, out ready signal):\n")
                        for hwio, ioMuxCaseList in stCon.fsmIoMuxCases.items():
                            if isinstance(ioMuxCaseList[0][0], HlsNetNodeWrite):
                                continue
                            rd = ioMuxCaseList[0][2]
                            out.write(f"      {hwio}, {rd}:\n")
                            for node, en, _, _ in ioMuxCaseList:
                                out.write(f"         id={node._id}, {en}\n")
                        #for en, rd in stCon.finalInputs:
                        #    out.write(f"      {en}, {rd}\n")

                        out.write("   outputs (io, out valid signal):\n")
                        #for en, vld in stCon.finalOutputs:
                        for hwio, ioMuxCaseList in stCon.fsmIoMuxCases.items():
                            if isinstance(ioMuxCaseList[0][0], HlsNetNodeRead):
                                continue
                            vld = ioMuxCaseList[0][2]
                            out.write(f"      {hwio}, {vld}:\n")
                            for node, en, _, _ in ioMuxCaseList:
                                out.write(f"         id={node._id}, {en}\n")
                            #out.write(f"      {en}, {vld}\n")

                        out.write("\n")
                elif isinstance(elm, ArchElementNoImplicitSync):
                    pass
                else:
                    raise NotImplementedError(elm)
        finally:
            if doClose:
                out.close()
