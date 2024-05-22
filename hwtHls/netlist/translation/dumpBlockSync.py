import html
import pydot
from typing import Dict, Set

from hwt.hwIO import HwIO
from hwtHls.llvm.llvmIr import MachineBasicBlock, MachineFunction, Register, TargetOpcode
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.translation.llvmMirToNetlist.machineBasicBlockMeta import MachineBasicBlockMeta
from hwtHls.ssa.translation.llvmMirToNetlist.machineEdgeMeta import \
    MachineEdge, MachineEdgeMeta, MACHINE_EDGE_TYPE


class HlsNetlistPassDumpBlockSync(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter, addLegend:bool=True):
        self.outStreamGetter = outStreamGetter
        self.addLegend = addLegend

    @staticmethod
    def dumpBlockSyncToDot(mf: MachineFunction,
                           blockSync: Dict[MachineBasicBlock, MachineBasicBlockMeta],
                           edgeMeta: Dict[MachineEdge, MachineEdgeMeta],
                           liveness: Dict[MachineBasicBlock, Dict[MachineBasicBlock, Set[Register]]],
                           regToIo: Dict[Register, HwIO],
                           addLegend:bool):
        P = pydot.Dot(f'"{mf.getName().str()}"', graph_type="digraph")

        if addLegend:
            legendTable = """<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td>discarded</td><td bgcolor="red"> </td></tr>
  <tr><td>reset</td><td bgcolor="orange"> </td></tr>
  <tr><td>backedge</td><td bgcolor="blue"> </td></tr>
  <tr><td>fowardedge</td><td bgcolor="green"> </td></tr>
</table>>"""
            legend = pydot.Node("legend", label=legendTable, style='filled', shape="plain")
            P.add_node(legend)

        blockNames = {}
        for i, b in  enumerate(mf):
            b: MachineBasicBlock
            color = "white"
            label = f"bb{i:d}"
            blockNames[b] = label
            name = f"bb{i:d}.{b.getName().str():s}"
            mbSync: MachineBasicBlockMeta = blockSync[b]
            flags = []
            if mbSync.needsStarter:
                flags.append("needsStarter")
            if mbSync.needsControl:
                flags.append("needsControl")
            if mbSync.rstPredeccessor:
                flags.append(f"rstPredeccessor=bb{mbSync.rstPredeccessor.getNumber()}")
            if mbSync.isLoopHeader:
                flags.append(f"isLoopHeader")
            if mbSync.isLoopHeaderOfFreeRunning:
                flags.append(f"isLoopHeaderOfFreeRunning")
            inputs = set()
            outputs = set()
            for instr in b:
                opc = instr.getOpcode()
                if opc in (TargetOpcode.HWTFPGA_CLOAD, TargetOpcode.HWTFPGA_CSTORE):
                    memOp = tuple(instr.memoperands())[0]
                    addrItem = (memOp.getAddrSpace(), memOp.getValue().getName().str())
                    if opc == TargetOpcode.HWTFPGA_CLOAD:
                        inputs.add(addrItem)
                    elif opc == TargetOpcode.HWTFPGA_CSTORE:
                        outputs.add(addrItem)
                    else:
                        raise AssertionError("All possible values should be already checked")
            inputs = sorted(inputs)
            outputs = sorted(outputs)

            body = (
                '        <table border="0" cellborder="1" cellspacing="0">\n'
                f'            <tr><td>{html.escape(name):s}</td></tr>\n'
                f"            <tr><td>{', '.join(flags)}</td></tr>\n"
                f"            <tr><td>IO in={inputs}</td></tr>\n"
                f"            <tr><td>IO out={outputs}</td></tr>\n"
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
                eMeta: MachineEdgeMeta = edgeMeta.get((b, suc), None)
                bodyText = []
                if lives:
                    bodyText.append(f'            <tr><td>liveRegs=[{",".join(lives)}]</td></tr>\n')

                if eMeta is None:
                    attrs = {"color": "red"}
                    bodyText.append(f'            <tr><td>missing edge meta</td></tr>\n')
                else:
                    if eMeta.inlineRstDataToEdge is not None:
                        rst = eMeta.inlineRstDataToEdge
                        bodyText.append(f'            <tr><td>inlineRstDataToEdge=({rst[0].getNumber()}, {rst[1].getNumber()})</td></tr>\n')
                    if eMeta.reuseDataAsControl is not None:
                        bodyText.append(f'            <tr><td>reuseDataAsControl={eMeta.reuseDataAsControl.virtRegIndex()}</td></tr>\n')
                    if eMeta.enteringLoops:
                        bodyText.append(f'            <tr><td>enteringLoops={eMeta.enteringLoops}</td></tr>\n')
                    if eMeta.reenteringLoops:
                        bodyText.append(f'            <tr><td>reenteringLoops={eMeta.reenteringLoops}</td></tr>\n')
                    if eMeta.exitingLoops:
                        bodyText.append(f'            <tr><td>exitingLoops={eMeta.exitingLoops}</td></tr>\n')

                    t = eMeta.etype
                    if t == MACHINE_EDGE_TYPE.RESET:
                        attrs = {"color": "orange"}
                    elif t == MACHINE_EDGE_TYPE.FORWARD:
                        attrs = {"color": "green"}
                    elif t == MACHINE_EDGE_TYPE.BACKWARD:
                        attrs = {"color": "blue"}
                    elif t == MACHINE_EDGE_TYPE.DISCARDED:
                        attrs = {"color": "red"}
                    else:
                        assert t == MACHINE_EDGE_TYPE.NORMAL, t
                        attrs = {}

                if not bodyText:
                    bodyText.append(f'            <tr><td></td></tr>\n')

                liveVarNodeLabel = f'e{b.getNumber():d}to{suc.getNumber():d}'
                p = pydot.Node(liveVarNodeLabel, fillcolor=color, style='filled', shape="plaintext", **attrs,
                               label=f'<\n        <table border="0" cellborder="1" cellspacing="0">\n{"".join(bodyText):s}        </table>>')
                P.add_node(p)

                e0 = pydot.Edge(blockNames[b], liveVarNodeLabel, **attrs)
                P.add_edge(e0)

                e1 = pydot.Edge(liveVarNodeLabel, blockNames[suc], **attrs)
                P.add_edge(e1)

        return P

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        from hwtHls.ssa.translation.llvmMirToNetlist.mirToNetlist import HlsNetlistAnalysisPassMirToNetlist
        toNetlist: HlsNetlistAnalysisPassMirToNetlist = netlist.getAnalysis(HlsNetlistAnalysisPassMirToNetlist)
        out, doClose = self.outStreamGetter(netlist.label)

        try:
            P = self.dumpBlockSyncToDot(toNetlist.mf, toNetlist.blockSync,
                                        toNetlist.edgeMeta, toNetlist.liveness,
                                        toNetlist.regToIo, self.addLegend)
            out.write(P.to_string())
        finally:
            if doClose:
                out.close()

