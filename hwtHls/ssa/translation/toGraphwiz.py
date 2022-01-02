import html
from pathlib import Path
from typing import List, Union, Dict, Optional, Tuple

from hdlConvertorAst.to.hdlUtils import iter_with_last
from hwtHls.hlsStreamProc.debugCodeSerializer import CopyBasicBlockLabelsToCode
from hwtHls.hlsStreamProc.statements import HlsStreamProcCodeBlock
from hwtHls.netlist.toGraphwiz import GraphwizNode, GraphwizLink, \
    HwtHlsNetlistToGraphwiz
from hwtHls.ssa.analysis.liveness import EdgeLivenessDict
from hwtHls.ssa.basicBlock import SsaBasicBlock
from hwtHls.ssa.instr import SsaInstr
from hwtHls.ssa.phi import SsaPhi
from hwtHls.ssa.translation.toHwtHlsNetlist.pipelineMaterialization import SsaSegmentToHwPipeline
from hwtHls.ssa.transformation.ssaPass import SsaPass


class SsaToGraphwiz():
    """
    Convert SSA to graphwiz for visualization.
    """

    def __init__(self, name: str):
        self.name = name
        self.nodes: List[GraphwizNode] = []
        self.links: List[GraphwizLink] = []
        self.obj_to_node: Dict[Union[SsaBasicBlock, Tuple[SsaBasicBlock, SsaBasicBlock]], GraphwizNode] = {}

    def construct(self, begin: SsaBasicBlock,
                  code: Optional[HlsStreamProcCodeBlock],
                  pipelines: Optional[List[List[SsaBasicBlock]]],
                  edge_var_live: Optional[EdgeLivenessDict]):
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
            code_body = '[shape=plaintext,fontname=monospace,label="' + self._escape(repr(code)).replace("\n", "\\l\\\n") + '\l"]'
            self.nodes.append(GraphwizNode("code", code_body))

    def _node_from_SsaBasicBlock(self, bb: SsaBasicBlock, is_start: bool, edge_var_live: Optional[EdgeLivenessDict]):
        try:
            return self.obj_to_node[bb]
        except KeyError:
            pass

        # node needs to be constructed before connecting because graph may contain loops
        node = GraphwizNode(f"bb{len(self.nodes)}", None)
        self.obj_to_node[bb] = node
        self.nodes.append(node)

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
            cond_str = "" if cond is None else self._escape(cond._name)
            body_rows.append(f"{{\\<{branch_label:s}\\> | <{branch_label:s}> {cond_str:s} }}")
            dst_node = self._node_from_SsaBasicBlock(dst_bb, False, edge_var_live)
            _src = f"{node.label:s}:{branch_label:s}"
            _dst = f"{dst_node.label}:begin"
            if edge_var_live is None:
                self.links.append(GraphwizLink(_src, _dst))
            else:
                var_rows = []
                for var in edge_var_live.get(bb, {}).get(dst_bb, ()):
                    n = html.escape(var._name)
                    var_rows.append(f"<tr><td>{n:s}</td></tr>")
                if var_rows:
                    link_var_node = GraphwizNode(f"bb{len(self.nodes)}", None)
                    link_var_node.body = '[shape=plaintext,fontname=monospace,label=<\n    <table color="gray">%s</table>\n>]' % "\n".join(var_rows)
                    self.obj_to_node[(bb, dst_bb)] = link_var_node
                    self.nodes.append(link_var_node)
                    self.links.append(GraphwizLink(_src, f"{link_var_node.label:s}"))
                    self.links.append(GraphwizLink(f"{link_var_node.label:s}", _dst))
                else:
                    self.links.append(GraphwizLink(_src, _dst))

        buff = []
        buff.append('[shape=record,fontname=monospace,label="{')
        for last, row in iter_with_last(body_rows):
            buff.append(row)
            if not last:
                buff.append("|\n")

        buff.append('}"]')
        node.body = "".join(buff)
        return node

    @staticmethod
    def _escape(s: str) -> str:
        return HwtHlsNetlistToGraphwiz._escape(s)

    def dumps(self):
        buff = ["digraph ", self.name, " {\n", " graph []\n"]
        for n in self.nodes:
            n.dumps(buff)
        for link in self.links:
            link.dumps(buff)
        buff.append("}\n")
        return "".join(buff)


class SsaPassDumpToDot(SsaPass):

    def __init__(self, file_name:str, extract_pipeline: bool=True):
        self.file_name = file_name
        self.extract_pipeline = extract_pipeline

    def apply(self, hls: "HlsStreamProc", to_ssa: "AstToSsa"):
        to_graphwiz = SsaToGraphwiz(Path(self.file_name).stem)
        if self.extract_pipeline:
            to_hw = SsaSegmentToHwPipeline(to_ssa.start, to_ssa.original_code_for_debug)
            to_hw.extract_pipeline()
            pipelines = [to_hw.pipeline, ]
            edge_var_live = to_hw.edge_var_live
        else:
            pipelines = None
            edge_var_live = None

        with open(self.file_name, "w") as f:
            to_graphwiz.construct(to_ssa.start, to_ssa.original_code_for_debug,
                                  pipelines, edge_var_live)
            f.write(to_graphwiz.dumps())
