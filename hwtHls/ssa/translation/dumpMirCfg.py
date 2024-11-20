import pydot

from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


def dumpMirCfgToDot(mf: MachineFunction):
    P = pydot.Dot(f'"{mf.getName().str()}"', graph_type="digraph")
    blockNames = {}
    for i, b in  enumerate(mf):
        b: MachineBasicBlock
        color = "white"
        name = f"bb{i:d}.{b.getName().str():s}"
        blockNames[b] = name
        p = pydot.Node(name, fillcolor=color, style='filled')
        P.add_node(p)

    for b in mf:
        b: MachineBasicBlock
        for suc in b.successors():
            suc: MachineBasicBlock
            edge = pydot.Edge(blockNames[b], blockNames[suc])
            P.add_edge(edge)
    return P


class SsaPassDumpMirCfg(SsaAnalysisPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnSsaModuleImpl(self, toLlvm:"ToLlvmIrTranslator"):
        llvm = toLlvm.llvm
        mf = llvm.getMachineFunction(llvm.main)
        assert mf
        out, doClose = self.outStreamGetter(llvm.main.getGlobalIdentifier())
        try:
            P = dumpMirCfgToDot(mf)
            out.write(P.to_string())
        finally:
            if doClose:
                out.close()
