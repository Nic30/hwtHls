import html
import pydot
from typing import Dict, Set, Tuple

from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineFunction, Register
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.utils import MachineBasicBlockSyncContainer
from hwt.synthesizer.interface import Interface


class HlsNetlistPassDumpBlockSync(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @staticmethod
    def dumpBlockSyncToDot(mf: MachineFunction,
                           blockSync: Dict[MachineBasicBlock, MachineBasicBlockSyncContainer],
                           backedges: Set[Tuple[MachineBasicBlock, MachineBasicBlock]],
                           liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                           regToIo:  Dict[Register, Interface]):
        P = pydot.Dot(f'"{mf.getName().str()}"', graph_type="digraph")
        
        legendTable = """<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td bgcolor="blue">backedge</td></tr>
</table>>"""
        legend = pydot.Node("legend", label=legendTable, style='filled', shape="plain")
        P.add_node(legend)
        
        blockNames = {}
        for i, b in  enumerate(mf):
            b: MachineBasicBlock
            color = "white"
            label = f"bb{i:d}"
            blockNames[b] = label
            name = f"bb.{i:d}.{b.getName().str():s}"
            mbSync: MachineBasicBlockSyncContainer = blockSync[b]
            flags = []
            if mbSync.needsStarter:
                flags.append("needsStarter")
            if mbSync.needsControl:
                flags.append("needsControl")
            if mbSync.rstPredeccessor:
                flags.append(f"rstPredeccessor=bb.{mbSync.rstPredeccessor.getNumber()}")
            body = (
                '<table border="0" cellborder="1" cellspacing="0">\n'
                f'            <tr><td>{html.escape(name):s}</td></tr>\n'
                f"            <tr><td>{', '.join(flags)}</td></tr>\n"
                f"            <tr><td>blockEn={html.escape(str(mbSync.blockEn))}</td></tr>\n"
                f"            <tr><td>orderingIn={html.escape(str(mbSync.orderingIn))}</td></tr>\n"
                f"            <tr><td>orderingOut={html.escape(str(mbSync.orderingOut))}</td></tr>\n"
                '        </table>'
            )
            p = pydot.Node(label, fillcolor=color, style='filled', shape="plaintext", label=f"<\n{body:s}\n>")
            P.add_node(p)
     
        for b in mf:
            b: MachineBasicBlock
            for suc in b.successors():
                suc: MachineBasicBlock
                eLive = liveness[b][suc]
                lives = [str(r) for r in sorted(r.virtRegIndex() for r in eLive if r not in regToIo)]
                
                body = (
                    '<table border="0" cellborder="1" cellspacing="0">\n'
                    f'            <tr><td>{",".join(lives)}</td></tr>\n'
                    '        </table>'
                )
                if (b, suc) in backedges:
                    attrs = {"color": "blue"}
                else:
                    attrs = {}

                liveVarNodeLabel = f'e{b.getNumber():d}to{suc.getNumber():d}'
                p = pydot.Node(liveVarNodeLabel, fillcolor=color, style='filled', shape="plaintext", label=f"<\n{body:s}\n>", **attrs)
                P.add_node(p)
     
                e0 = pydot.Edge(blockNames[b], liveVarNodeLabel, **attrs)
                P.add_edge(e0)
                e1 = pydot.Edge(liveVarNodeLabel, blockNames[suc], **attrs)
                P.add_edge(e1)

        return P
        
    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        from hwtHls.ssa.translation.llvmToMirAndMirToHlsNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
        toNetlist: HlsNetlistAnalysisPassMirToNetlist = netlist.requestAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        out, doClose = self.outStreamGetter(netlist.label)
        
        try:
            P = self.dumpBlockSyncToDot(toNetlist.mf, toNetlist.blockSync, toNetlist.backedges, toNetlist.liveness, toNetlist.regToIo)
            out.write(P.to_string())
        finally:
            if doClose:
                out.close()

