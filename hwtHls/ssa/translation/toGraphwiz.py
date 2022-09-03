import html
import pydot
from typing import List, Union, Dict, Optional, Tuple, Set

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.debugCodeSerializer import CopyBasicBlockLabelsToCode
from hwtHls.frontend.ast.statements import HlsStmCodeBlock
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.value import SsaValue

EdgeLivenessDict = Dict[SsaBasicBlock, Dict[SsaBasicBlock, Set[SsaValue]]]


class SsaToGraphwiz():
    """
    Convert SSA to graphwiz for visualization.
    """

    def __init__(self, name: str):
        self.name = name
        self.graph = pydot.Dot(f'"{name}"')
        self.obj_to_node: Dict[Union[SsaBasicBlock, Tuple[SsaBasicBlock, SsaBasicBlock]], pydot.Node] = {}

    def construct(self, begin: SsaBasicBlock,
                  code: Optional[HlsStmCodeBlock]):
        g = self.graph
        self._node_from_SsaBasicBlock(begin, True)

        if code is not None:
            CopyBasicBlockLabelsToCode().visit(begin)
            g.add_node(pydot.Node("code", shape="plaintext", fontname="monospace", label='"' + html.escape(repr(code)).replace("\n", "\\l\\\n") + '\l"'))

    def _node_from_SsaBasicBlock(self, bb: SsaBasicBlock, is_start: bool):
        try:
            return self.obj_to_node[bb]
        except KeyError:
            pass
        g = self.graph
        # node needs to be constructed before connecting because graph may contain loops
        node = pydot.Node(f"bb{len(g.obj_dict['nodes'])}", shape="plaintext")
        g.add_node(node)
        self.obj_to_node[bb] = node

        # construct new node
        topStr = html.escape('<start> ') if is_start else ''
        topLabel = html.escape(bb.label).replace('\n', ' ')
        bodyRows = [f'    <tr port="begin"><td colspan="2">{topStr:s}{topLabel:s}:</td></tr>']
        for phi in bb.phis:
            phi: SsaPhi
            ops = ", ".join(
                f"[{o._name if isinstance(o, SsaInstr) else repr(o)}, {b.label:s}]"
                for (o, b) in phi.operands
            )
            bodyRows.append(f'    <tr><td colspan="2">{html.escape(phi._name)} = phi {html.escape(repr(phi._dtype))} {html.escape(ops):s}</td></tr>')

        for stm in bb.body:
            stmStr = html.escape(repr(stm))
            bodyRows.append(f'    <tr><td colspan="2">{stmStr}</td></tr>')

        for i, (cond, dst_bb, _) in enumerate(bb.successors.targets):
            branch_label = f"br{i:d}"
            cond_str = "" if cond is None\
                else html.escape(cond._name) if isinstance(cond, RtlSignal) else\
                html.escape(cond._name) if isinstance(cond, SsaValue) and cond._name else repr(cond)
            cond_str = html.escape(cond_str)
            bodyRows.append(f'    <tr port="{branch_label:s}"><td>{branch_label}</td><td>{cond_str:s}</td></tr>')
            dst_node = self._node_from_SsaBasicBlock(dst_bb, False)
            _src = f"{node.get_name():s}:{branch_label:s}"
            _dst = f"{dst_node.get_name()}:begin"
            e = pydot.Edge(_src, _dst)
            g.add_edge(e)
          

        bodyStr = "\n".join(bodyRows)
        label = f'<<table border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
        node.set("label", label) 
        return node

    def dumps(self):
        return self.graph.to_string()


class SsaPassDumpToDot(SsaPass):

    def __init__(self, outStreamGetter:OutputStreamGetter, extractPipeline: bool=False):
        self.outStreamGetter = outStreamGetter
        if extractPipeline:
            raise NotImplementedError()
        self.extractPipeline = extractPipeline

    def apply(self, hls: "HlsScope", toSsa: "HlsAstToSsa"):
        name = toSsa.label
        to_graphwiz = SsaToGraphwiz(name)
        out, doClose = self.outStreamGetter(name)
        try:
            to_graphwiz.construct(toSsa.start, toSsa.original_code_for_debug)
            out.write(to_graphwiz.dumps())
        finally:
            if doClose:
                out.close()
