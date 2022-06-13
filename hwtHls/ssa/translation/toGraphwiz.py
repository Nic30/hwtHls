import html
import pydot
from typing import List, Union, Dict, Optional, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwt.synthesizer.rtlLevel.rtlSignal import RtlSignal
from hwtHls.frontend.ast.debugCodeSerializer import CopyBasicBlockLabelsToCode
from hwtHls.frontend.ast.statements import HlsStmCodeBlock
from hwtHls.netlist.translation.toGraphwiz import HwtHlsNetlistToGraphwiz
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.transformation.ssaPass import SsaPass
from hwtHls.ssa.value import SsaValue


class SsaToGraphwiz():
    """
    Convert SSA to graphwiz for visualization.
    """

    def __init__(self, name: str):
        self.name = name
        self.graph = pydot.Dot(f'"{name}"')
        self.obj_to_node: Dict[Union[SsaBasicBlock, Tuple[SsaBasicBlock, SsaBasicBlock]], pydot.Node] = {}

    def construct(self, begin: SsaBasicBlock,
                  code: Optional[HlsStmCodeBlock],
                  pipelines: Optional[List[List[SsaBasicBlock]]],
                  edge_var_live: Optional[EdgeLivenessDict]):
        g = self.graph
        self._node_from_SsaBasicBlock(begin, True, edge_var_live)
        if pipelines is not None:
            bb_to_pipe_i = {}
            for i, pipe in enumerate(pipelines):
                for bb in pipe:
                    bb_to_pipe_i[bb] = i

            for bb, n in self.obj_to_node.items():
                if not isinstance(bb, SsaBasicBlock):
                    continue
                pipe_i = bb_to_pipe_i[bb]
                n.body = n.body.replace("<begin> ", f"<begin> p{pipe_i} ")

        if code is not None:
            CopyBasicBlockLabelsToCode().visit(begin)
            g.add_node(pydot.Node("code", shape="plaintext", fontname="monospace", label='"' + self._escape(repr(code)).replace("\n", "\\l\\\n") + '\l"'))

    def _node_from_SsaBasicBlock(self, bb: SsaBasicBlock, is_start: bool, edge_var_live: Optional[EdgeLivenessDict]):
        try:
            return self.obj_to_node[bb]
        except KeyError:
            pass
        g = self.graph
        # node needs to be constructed before connecting because graph may contain loops
        node = pydot.Node(f"bb{len(g.obj_dict['nodes'])}", shape="record", fontname="monospace")
        g.add_node(node)
        self.obj_to_node[bb] = node

        # construct new node
        top_str = '\<start\> ' if is_start else ''
        body_rows = [f"<begin> {top_str:s}{bb.label:s}:"]
        for phi in bb.phis:
            phi: SsaPhi
            ops = ", ".join(
                f"[{self._escape(o._name if isinstance(o, SsaInstr) else repr(o))}, {b.label:s}]"
                for (o, b) in phi.operands
            )
            body_rows.append(f"{self._escape(phi._name)} = phi {self._escape(repr(phi._dtype))} {ops:s}\\l")

        for stm in bb.body:
            body_rows.append(self._escape(repr(stm)) + "\\l")

        for i, (cond, dst_bb) in enumerate(bb.successors.targets):
            branch_label = f"br{i:d}"
            cond_str = "" if cond is None\
                else self._escape(cond._name) if isinstance(cond, RtlSignal) else\
                self._escape(cond._name) if isinstance(cond, SsaValue) and cond._name else self._escape(repr(cond))
            body_rows.append(f"{{\\<{branch_label:s}\\> | <{branch_label:s}> {cond_str:s} }}")
            dst_node = self._node_from_SsaBasicBlock(dst_bb, False, edge_var_live)
            _src = f"{node.get_name():s}:{branch_label:s}"
            _dst = f"{dst_node.get_name()}:begin"
            if edge_var_live is None:
                e = pydot.Edge(_src, _dst)
                g.add_edge(e)
            else:
                var_rows = []
                for var in edge_var_live.get(bb, {}).get(dst_bb, ()):
                    n = html.escape(var._name)
                    var_rows.append(f"<tr><td>{n:s}</td></tr>")
                if var_rows:
                    link_var_node = pydot.Node(f"bb{len(self.nodes):d}", shape="plaintext", fontname="monospace", label='<\n    <table color="gray">%s</table>' % "\n".join(var_rows))
                    self.obj_to_node[(bb, dst_bb)] = link_var_node
                    g.add_node(link_var_node)
                    g.add_edge(pydot.Edge(_src, f"{link_var_node.get_name():s}"))
                    g.add_edge(pydot.Edge(f"{link_var_node.get_name():s}", _dst))
                else:
                    g.add_edge(pydot.Edge(_src, _dst))

        buff = []
        buff.append('"{')
        for last, row in iter_with_last(body_rows):
            buff.append(row)
            if not last:
                buff.append("|\n")

        buff.append('}"')
        node.set("label", "".join(buff)) 
        return node

    @staticmethod
    def _escape(s: str) -> str:
        return HwtHlsNetlistToGraphwiz._escape(s)

    def dumps(self):
        return self.graph.to_string()


class SsaPassDumpToDot(SsaPass):

    def __init__(self, outStreamGetter:OutputStreamGetter, extractPipeline: bool=False):
        self.outStreamGetter = outStreamGetter
        if extractPipeline:
            raise NotImplementedError()
        self.extractPipeline = extractPipeline

    def apply(self, hls: "HlsScope", to_ssa: "HlsAstToSsa"):
        name = to_ssa.label
        to_graphwiz = SsaToGraphwiz(name)
        # if self.extractPipeline:
        #    to_hw = SsaSegmentToHwPipeline(to_ssa.start, to_ssa.original_code_for_debug)
        #    to_hw.extract_pipeline()
        #    pipelines = [to_hw.pipeline, ]
        #    edge_var_live = to_hw.edge_var_live
        # else:
        pipelines = None
        edge_var_live = None
        out, doClose = self.outStreamGetter(name)
        try:
            to_graphwiz.construct(to_ssa.start, to_ssa.original_code_for_debug,
                                  pipelines, edge_var_live)
            out.write(to_graphwiz.dumps())
        finally:
            if doClose:
                out.close()
