import pydot

from hwtHls.llvm.llvmIr import MachineFunction, MachineBasicBlock
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator
from hwtHls.typingFuture import override


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


class SsaPassDumpMirCfg(SsaPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnSsaModuleImpl(self, toSsa: "HlsAstToSsa"):
        tr: ToLlvmIrTranslator = toSsa.start
        assert isinstance(tr, ToLlvmIrTranslator), tr
        mf = tr.llvm.getMachineFunction(tr.llvm.main)
        assert mf
        out, doClose = self.outStreamGetter(tr.llvm.main.getGlobalIdentifier())
        try:
            P = dumpMirCfgToDot(mf)
            out.write(P.to_string())
        finally:
            if doClose:
                out.close()
