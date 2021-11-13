import html
from itertools import zip_longest
from typing import List, Union, Dict

from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.netlist.nodes.io import HlsRead, HlsWrite
from hwtHls.netlist.nodes.ops import AbstractHlsOp, HlsConst, HlsOperation
from hwtHls.netlist.nodes.ports import HlsOperationOut


class GraphwizNode():

    def __init__(self, label:str, body: Union[None, str]):
        self.label = label
        self.body = body

    def dumps(self, buff):
        label = self.label
        body = self.body
        if body is None:
            buff.append(f" {label:s};\n")
        else:
            buff.append(f' {label:s} {body:s};\n')


class GraphwizLink():

    def __init__(self, src, dst, style=""):
        self.src = src
        self.dst = dst
        self.style = style

    def dumps(self, buff):
        buff.append(" ")
        buff.append(self.src)
        buff.append("->")
        buff.append(self.dst)
        buff.append(self.style)
        buff.append(";\n")


class HwtHlsNetlistToGraphwiz():
    """

    https://renenyffenegger.ch/notes/tools/Graphviz/examples/index
    """

    def __init__(self, name: str):
        self.name = name
        self.nodes: List[GraphwizNode] = []
        self.links: List[GraphwizLink] = []
        self.obj_to_node: Dict[AbstractHlsOp, GraphwizNode] = {}

    def construct(self, nodes: List[AbstractHlsOp]):
        for n in nodes:
            self._node_from_AbstractHlsOp(n)

    def _node_from_AbstractHlsOp(self, obj: AbstractHlsOp):
        try:
            return self.obj_to_node[obj]
        except KeyError:
            pass

        # node needs to be constructed before connecting because graph may contain loops
        node = GraphwizNode(f"n{len(self.nodes)}", None)
        self.obj_to_node[obj] = node
        self.nodes.append(node)

        # construct new node
        input_rows = []
        try:
            for node_in_i, drv in enumerate(obj.dependsOn):
                input_rows.append(f"<td port='i{node_in_i:d}'>i{node_in_i:d}</td>")
                if drv is not None:
                    drv: HlsOperationOut
                    drv_node = self._node_from_AbstractHlsOp(drv.obj)
                    self.links.append(GraphwizLink(f"{drv_node.label:s}:o{drv.out_i:d}", f"{node.label:s}:i{node_in_i:d}"))
            for shadow_dst in obj.debug_iter_shadow_connection_dst():
                shadow_dst_node = self._node_from_AbstractHlsOp(shadow_dst)
                self.links.append(GraphwizLink(f"{node.label:s}", f"{shadow_dst_node.label:s}", style="[style=dashed, color=grey]"))
        except:
            raise AssertionError("defective node", obj)

        output_rows = []
        for node_out_i, _ in enumerate(obj.usedBy):
            # dsts: List[HlsOperationIn]
            output_rows.append(f"<td port='o{node_out_i:d}'>o{node_out_i:d}</td>")

        buff = []
        buff.append('''[shape=plaintext
    label=<
        <table border="0" cellborder="1" cellspacing="0">\n''')
        if isinstance(obj, HlsConst):
            label = repr(obj.val)
        elif isinstance(obj, HlsOperation):
            label = obj.operator.id
        elif isinstance(obj, HlsRead):
            label = repr(obj)
        elif isinstance(obj, HlsWrite):
            label = f"<{obj.__class__.__name__} {getSignalName(obj.dst)}>"
        else:
            label = obj.__class__.__name__

        buff.append(f'            <tr><td colspan="2">{html.escape(label):s}</td></tr>\n')
        for i, o in zip_longest(input_rows, output_rows, fillvalue="<td></td>"):
            buff.append(f"            <tr>{i:s}{o:s}</tr>\n")
        buff.append('        </table>>')

        buff.append(']')
        node.body = "".join(buff)
        return node

    @staticmethod
    def _escape(s: str) -> str:
        return s.replace("<", "\\<").replace(">", "\\>").replace("|", "\\|").replace('"', '\\"')

    def dumps(self):
        buff = ["digraph ", self.name, " {\n", ]
        for n in self.nodes:
            n.dumps(buff)
        for link in self.links:
            link.dumps(buff)
        buff.append("}\n")
        return "".join(buff)


class HlsNetlistPassDumpToDot():

    def __init__(self, file_name:str):
        self.file_name = file_name

    def apply(self, to_hw: "SsaSegmentToHwPipeline"):
        to_graphwiz = HwtHlsNetlistToGraphwiz("top")
        with open(self.file_name, "w") as f:
            to_graphwiz.construct(to_hw.hls.inputs + to_hw.hls.nodes + to_hw.hls.outputs)
            f.write(to_graphwiz.dumps())

