import html
from itertools import zip_longest
import pydot
from typing import List, Union, Dict

from hwt.synthesizer.interfaceLevel.unitImplHelpers import getSignalName
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.io import HlsNetNodeRead, HlsNetNodeWrite
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter


class HwtHlsNetlistToGraphwiz():
    """

    https://renenyffenegger.ch/notes/tools/Graphviz/examples/index
    """

    def __init__(self, name: str):
        self.name = name
        self.graph = pydot.Dot(f'"{name}"')
        self.obj_to_node: Dict[HlsNetNode, pydot.Node] = {}

    def construct(self, nodes: List[HlsNetNode]):
        for n in nodes:
            self._node_from_HlsNetNode(n)
        
        legendTable = """<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td bgcolor="LightGreen">HlsNetNodeRead</td></tr>
  <tr><td bgcolor="LightBlue">HlsNetNodeWrite</td></tr>
  <tr><td bgcolor="plum">HlsNetNodeConst</td></tr>
  <tr><td bgcolor="gray">shadow connection</td></tr>
  <tr><td bgcolor="LightCoral">HlsNetNodeOutLazy</td></tr>
</table>>"""
        legend = pydot.Node("legend", label=legendTable, style='filled', shape="plain")
        self.graph.add_node(legend)

    def _node_from_HlsNetNode(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        try:
            return self.obj_to_node[obj]
        except KeyError:
            pass

        g = self.graph
        if isinstance(obj, HlsNetNodeOutLazy):
            color = "LightCoral"
        elif isinstance(obj, HlsNetNodeRead):
            color = "LightGreen"
        elif isinstance(obj, HlsNetNodeWrite):
            color = "LightBlue"
        elif isinstance(obj, HlsNetNodeConst):
            color = "plum"
        else:
            color = "white"
        # node needs to be constructed before connecting because graph may contain loops
        node = pydot.Node(f"n{len(g.obj_dict['nodes'])}", fillcolor=color, style='filled', shape="plaintext")
        g.add_node(node)

        self.obj_to_node[obj] = node

        # construct new node
        input_rows = []
        if isinstance(obj, HlsNetNode):
            try:
                for node_in_i, drv in enumerate(obj.dependsOn):
                    input_rows.append(f"<td port='i{node_in_i:d}'>i{node_in_i:d}</td>")
                    if drv is not None:
                        drv: Union[HlsNetNodeOut, HlsNetNodeOutLazy]
                        if isinstance(drv, HlsNetNodeOut):
                            drv_node = self._node_from_HlsNetNode(drv.obj)
                            src = f"{drv_node.get_name():s}:o{drv.out_i:d}"
                        else:
                            drv_node = self._node_from_HlsNetNode(drv)
                            src = f"{drv_node.get_name():s}:o0"
    
                        e = pydot.Edge(src, f"{node.get_name():s}:i{node_in_i:d}")
                        g.add_edge(e)
    
                for shadow_dst in obj.debug_iter_shadow_connection_dst():
                    shadow_dst_node = self._node_from_HlsNetNode(shadow_dst)
                    e = pydot.Edge(f"{node.get_name():s}", f"{shadow_dst_node.get_name():s}", style="dashed", color="gray")
                    g.add_edge(e)
    
            except:
                raise AssertionError("defective node", obj)
        else:
            assert isinstance(obj, HlsNetNodeOutLazy), obj
        output_rows = []
        if isinstance(obj, HlsNetNode):
            for node_out_i, _ in enumerate(obj.usedBy):
                # dsts: List[HlsNetNodeIn]
                output_rows.append(f"<td port='o{node_out_i:d}'>o{node_out_i:d}</td>")
        else:
            output_rows.append("<td port='o0'>o0</td>")

        buff = []
        buff.append('''<
        <table border="0" cellborder="1" cellspacing="0">\n''')
        if isinstance(obj, HlsNetNodeConst):
            label = repr(obj.val)
        elif isinstance(obj, HlsNetNodeOperator):
            label = obj.operator.id
        elif isinstance(obj, HlsNetNodeRead):
            label = repr(obj)
        elif isinstance(obj, HlsNetNodeWrite):
            label = f"<{obj.__class__.__name__} {getSignalName(obj.dst)}>"
        else:
            label = obj.__class__.__name__

        buff.append(f'            <tr><td colspan="2">{html.escape(label):s} {obj._id}</td></tr>\n')
        for i, o in zip_longest(input_rows, output_rows, fillvalue="<td></td>"):
            buff.append(f"            <tr>{i:s}{o:s}</tr>\n")
        buff.append('        </table>>')

        node.set("label", "".join(buff))
        return node

    @staticmethod
    def _escape(s: str) -> str:
        return s.replace("<", "\\<").replace(">", "\\>").replace("|", "\\|").replace('"', '\\"').replace("{", "\\{").replace("}", "\\}")

    def dumps(self):
        return self.graph.to_string()


class HlsNetlistPassDumpToDot(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        name = netlist.label
        toGraphwiz = HwtHlsNetlistToGraphwiz(name)
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz.construct(netlist.inputs + netlist.nodes + netlist.outputs)
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()

