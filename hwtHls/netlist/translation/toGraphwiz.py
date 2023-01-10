import html
from itertools import zip_longest
import pydot
from typing import List, Union, Dict

from hwt.hdl.operatorDefs import COMPARE_OPS
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopGate import HlsLoopGate, HlsLoopGateStatus
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    _reprMinify
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.netlist.nodes.orderable import HOrderingVoidT, HExternalDataDepT


class HwtHlsNetlistToGraphwiz():
    """
    Generate a Graphwiz (dot) diagram of the netlist.
    """

    def __init__(self, name: str, nodes: List[HlsNetNode]):
        self.name = name
        self.allNodes = UniqList(nodes)
        self.graph = pydot.Dot(f'"{name}"')
        self.obj_to_node: Dict[HlsNetNode, pydot.Node] = {}
        self.nodeCounter = 0

    def _getNewNodeId(self):
        i = self.nodeCounter
        self.nodeCounter += 1
        return i

    def construct(self,):
        for n in self.allNodes:
            self._node_from_HlsNetNode(n)
        
        self.graph.add_node(self._constructLegend())
    
    def _constructLegend(self):
        legendTable = """<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td bgcolor="LightGreen">HlsNetNodeRead, HlsNetNodeReadSync</td></tr>
  <tr><td bgcolor="LightBlue">HlsNetNodeWrite</td></tr>
  <tr><td bgcolor="plum">HlsNetNodeConst</td></tr>
  <tr><td bgcolor="Chartreuse">HlsNetNodeExplicitSync</td></tr>
  <tr><td bgcolor="MediumSpringGreen">HlsLoopGate, HlsLoopGateStatus, HlsProgramStarter</td></tr>
  <tr><td bgcolor="gray">shadow connection</td></tr>
  <tr><td bgcolor="LightCoral">HlsNetNodeOutLazy</td></tr>
</table>>"""
        return pydot.Node("legend", label=legendTable, style='filled', shape="plain")

    def _getColor(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        if isinstance(obj, HlsNetNodeOutLazy):
            color = "LightCoral"
        elif isinstance(obj, (HlsNetNodeRead, HlsNetNodeReadSync)):
            color = "LightGreen"
        elif isinstance(obj, HlsNetNodeWrite):
            color = "LightBlue"
        elif isinstance(obj, HlsNetNodeConst):
            color = "plum"
        elif isinstance(obj, HlsNetNodeExplicitSync):
            color = "Chartreuse"
        elif isinstance(obj, (HlsLoopGate, HlsLoopGateStatus, HlsProgramStarter)):
            color = "MediumSpringGreen"
        else:
            color = "white"
        return color

    def _getGraph(self, n: HlsNetNode):
        return self.graph
        
    def _node_from_HlsNetNode(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        try:
            return self.obj_to_node[obj]
        except KeyError:
            pass
        g = self._getGraph(obj)
        # node needs to be constructed before connecting because graph may contain loops
        # fillcolor=color, style='filled', 
        node = pydot.Node(f"n{self._getNewNodeId()}", shape="plaintext")
        g.add_node(node)

        self.obj_to_node[obj] = node

        # construct new node
        input_rows = []
        if isinstance(obj, HlsNetNode):
            try:
                for node_in_i, (inp, dep) in enumerate(zip(obj._inputs, obj.dependsOn)):
                    if isinstance(dep, HlsNetNodeOut) and dep.obj not in self.allNodes:
                        continue
                    if inp.name is not None:
                        inpName = inp.name
                    else:
                        inpName = f"i{node_in_i:d}"
                    input_rows.append(f"<td port='i{node_in_i:d}'>{inpName:s}</td>")
                    if dep is not None:
                        dep: Union[HlsNetNodeOut, HlsNetNodeOutLazy]
                        if isinstance(dep, HlsNetNodeOut):
                            dep_node = self._node_from_HlsNetNode(dep.obj)
                            src = f"{dep_node.get_name():s}:o{dep.out_i:d}"
                        else:
                            dep_node = self._node_from_HlsNetNode(dep)
                            src = f"{dep_node.get_name():s}:o0"
                        attrs = {}
                        if dep._dtype is HOrderingVoidT or dep._dtype is HExternalDataDepT:
                            attrs["style"] = "dotted"
                        e = pydot.Edge(src, f"{node.get_name():s}:i{node_in_i:d}", **attrs)
                        self.graph.add_edge(e)
    
                for shadow_dst in obj.debug_iter_shadow_connection_dst():
                    if isinstance(shadow_dst, HlsNetNode) and shadow_dst not in self.allNodes:
                        continue
                    shadow_dst_node = self._node_from_HlsNetNode(shadow_dst)
                    e = pydot.Edge(f"{node.get_name():s}", f"{shadow_dst_node.get_name():s}", style="dashed", color="gray")
                    self.graph.add_edge(e)
    
            except:
                raise AssertionError("defective node", obj)
        else:
            assert isinstance(obj, HlsNetNodeOutLazy), obj
        output_rows = []
        if isinstance(obj, HlsNetNode):
            for node_out_i, out in enumerate(obj._outputs):
                if out.name is not None:
                    outName = out.name
                else:
                    outName = f"o{node_out_i:d}"
                output_rows.append(f"<td port='o{node_out_i:d}'>{outName:s}</td>")
        else:
            output_rows.append("<td port='o0'>o0</td>")

        buff = []
        
        color = self._getColor(obj) if obj in self.allNodes else "orange"
        buff.append(f'''<
        <table bgcolor="{color:s}" border="0" cellborder="1" cellspacing="0">\n''')

        if isinstance(obj, HlsNetNodeConst):
            label = f"{obj.val} {obj._id}"
        elif isinstance(obj, HlsNetNodeOperator):
            if obj.operator in COMPARE_OPS:
                dep = obj.dependsOn[0]
                if dep is None:
                    t = "<INVALID>"
                else:
                    t = obj.dependsOn[0]._dtype
            else:
                t = obj._outputs[0]._dtype

            label = f"{obj.operator.id} {obj._id} {t}"
        elif isinstance(obj, (HlsNetNodeRead, HlsNetNodeWrite, HlsLoopGateStatus)):
            label = _reprMinify(obj)
        else:
            label = f"{obj.__class__.__name__} {obj._id}"
        
        buff.append(f'            <tr><td colspan="2">{html.escape(label):s}</td></tr>\n')
        for i, o in zip_longest(input_rows, output_rows, fillvalue="<td></td>"):
            buff.append(f"            <tr>{i:s}{o:s}</tr>\n")
        buff.append('        </table>>')

        node.set("label", "".join(buff))
        return node

    def dumps(self):
        return self.graph.to_string()


class HlsNetlistPassDumpToDot(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    def apply(self, hls: "HlsScope", netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz = HwtHlsNetlistToGraphwiz(name, netlist.iterAllNodes())
            toGraphwiz.construct()
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()

