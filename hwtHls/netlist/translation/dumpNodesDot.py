import html
from itertools import zip_longest
import pydot
from typing import List, Union, Dict, Optional, Callable, Tuple

from hwt.hdl.operatorDefs import COMPARE_OPS, AllOps, OpDefinition
from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.IoClusterCore import HlsNetNodeIoClusterCore
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn, HlsNetNodeAggregate
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopControl import HlsNetNodeLoopStatus
from hwtHls.netlist.nodes.node import HlsNetNode, NODE_ITERATION_TYPE
from hwtHls.netlist.nodes.ops import HlsNetNodeOperator
from hwtHls.netlist.nodes.ports import HlsNetNodeOut, HlsNetNodeOutLazy, \
    _reprMinify, HlsNetNodeIn
from hwtHls.netlist.nodes.programStarter import HlsProgramStarter
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.readSync import HlsNetNodeReadSync
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod
from hwtHls.netlist.transformation.hlsNetlistPass import HlsNetlistPass
from hwtHls.platform.fileUtils import OutputStreamGetter


class HwtHlsNetlistToGraphwiz():
    """
    Generate a Graphwiz (dot) diagram of the netlist.
    """

    def __init__(self, name: str, nodes: List[HlsNetNode], expandAggregates: bool, addLegend: bool):
        """
        :attention: if expandAggregates==True the nodes should contain also parent aggregates
            and parent aggregate position in nodes list must be before its children.
        """
        self.name = name
        self.allNodes = UniqList(nodes)
        self.graph = pydot.Dot(f'"{name}"')
        self.obj_to_node: Dict[HlsNetNode, pydot.Node] = {}
        self.nodeCounter = 0
        self.expandAggregates = expandAggregates
        self.addLegend = addLegend
        self._edgeFilterFn: Optional[Callable[[HlsNetNodeOut, HlsNetNodeIn], bool]] = None
        self._expandedNodes: Dict[Union[HlsNetNodeAggregate, Tuple[HlsNetNodeAggregate, int]], pydot.Cluster] = {}
        self._parentOfNode: Dict[HlsNetNode, Tuple[HlsNetNodeAggregate, int]] = {}

    def _constructLegend(self):
        legendTable = """<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td bgcolor="LightGreen">HlsNetNodeRead, HlsNetNodeReadSync</td></tr>
  <tr><td bgcolor="LightBlue">HlsNetNodeWrite</td></tr>
  <tr><td bgcolor="plum">HlsNetNodeConst</td></tr>
  <tr><td bgcolor="Chartreuse">HlsNetNodeExplicitSync</td></tr>
  <tr><td bgcolor="MediumSpringGreen">HlsNetNodeLoopStatus, HlsProgramStarter</td></tr>
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
        elif isinstance(obj, (HlsNetNodeLoopStatus, HlsProgramStarter)):
            color = "MediumSpringGreen"
        else:
            color = "white"
        return color

    def _getNewNodeId(self):
        i = self.nodeCounter
        self.nodeCounter += 1
        return i

    def _constructNodeHierarchy(self):
        assert self.expandAggregates
        allNodes = self.allNodes
        parentOfNode = self._parentOfNode
        expandedNodes = self._expandedNodes
        for parent in allNodes:
            if isinstance(parent, HlsNetNodeAggregate):
                parent: HlsNetNodeAggregate
                label = f"{parent.__class__.__name__} {parent._id:d} {self._formatNodeScheduleTime(parent)}{' ' + parent.name if parent.name else ''}"
                clusterNode = pydot.Cluster(f"n{self._getNewNodeId()}", label=f'"{html.escape(label)}"')
                g = self._getGraph(parent)
                g.add_subgraph(clusterNode)
                expandedNodes[parent] = clusterNode

                for n in parent._subNodes:
                    assert n not in parentOfNode, ("Each node is supposed to have just a single parent", n, parentOfNode[n], parent)
                    parentOfNode[n] = parent

                if isinstance(parent, ArchElement):
                    # parentOfNode nodes are already preset in the case that there
                    # are some nodes which are not placed in clock windows yet
                    parent: ArchElement
                    for clkI, nodes in parent.iterStages():
                        if not nodes:
                            continue
                        label = f"{clkI}"
                        clockWindowClusterNode = pydot.Cluster(f"n{self._getNewNodeId()}", label=f'"{html.escape(label)}"')
                        clusterNode.add_subgraph(clockWindowClusterNode)
                        expandedNodes[(parent, clkI)] = clockWindowClusterNode
                        for n in nodes:
                            parentOfNode[n] = (parent, clkI)

    def construct(self):
        expandAggregates = self.expandAggregates
        if expandAggregates:
            self._constructNodeHierarchy()
        for n in self.allNodes:
            if expandAggregates and n in self._expandedNodes:
                continue
            if isinstance(n, HlsNetNodeConst) and len(n.usedBy[0]) == 1:
                continue  # const inlined into user node
            self._node_from_HlsNetNode(n)
        if self.addLegend:
            self.graph.add_node(self._constructLegend())

    def _getGraph(self, n: HlsNetNode):
        if self.expandAggregates:
            parent = self._parentOfNode.get(n, None)
            if parent is None:
                return self.graph
            else:
                return self._expandedNodes[parent]
        else:
            return self.graph

    @staticmethod
    def _formatScheduleTime(time: SchedTime, clkPeriod: SchedTime):
        clkI = indexOfClkPeriod(time, clkPeriod)
        if clkI < 0:
            raise NotImplementedError()
        inClkPos = time - clkI * clkPeriod
        return f" {clkI}clk+{inClkPos}"

    @classmethod
    def _formatNodeScheduleTime(cls, node: Union[HlsNetNode, HlsNetNodeOutLazy]):
        if isinstance(node, HlsNetNodeOutLazy):
            return ""
        t = node.scheduledZero
        if t is None:
            return ""
        else:
            clkPeriod: SchedTime = node.netlist.normalizedClkPeriod
            return cls._formatScheduleTime(t, clkPeriod)

    def _node_from_HlsNetNode(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        try:
            return self.obj_to_node[obj]
        except KeyError:
            pass
        g = self._getGraph(obj)
        # node needs to be constructed before connecting because graph may contain loops
        # fillcolor=color, style='filled',

        bgcolor, color = self._getColor(obj) if obj in self.allNodes else ("orange", "black")
        node = pydot.Node(f"n{self._getNewNodeId()}", shape="plaintext", bgcolor=bgcolor, color=color, fontcolor=color)
        g.add_node(node)
        self.obj_to_node[obj] = node

        edgeFilter = self._edgeFilterFn
        expandAggregates = self.expandAggregates
        # construct new node
        input_rows = []
        if isinstance(obj, HlsNetNode):
            try:
                scheduledIn = obj.scheduledIn
                clkPeriod = obj.netlist.normalizedClkPeriod
                if scheduledIn is None:
                    scheduledIn = (None for _ in obj._inputs)

                for node_in_i, (inp, dep, time) in enumerate(zip(obj._inputs, obj.dependsOn, scheduledIn)):
                    if isinstance(dep, HlsNetNodeOut) and dep.obj not in self.allNodes:
                        # connected to something which is not part of selected graph
                        continue

                    if inp.name is not None:
                        inpName = inp.name
                    else:
                        inpName = f"i{node_in_i:d}"

                    if time is not None:
                        inpName = f"{inpName} {self._formatScheduleTime(time, clkPeriod)}"

                    isInlinableConst = (isinstance(dep, HlsNetNodeOut) and
                                        isinstance(dep.obj, HlsNetNodeConst) and
                                        len(dep.obj.usedBy) == 1)
                    edgeRequired = dep is not None and (edgeFilter is None or edgeFilter(dep, inp))
                    if edgeRequired and isInlinableConst:
                        ir = f"<td port='i{node_in_i:d}'>{inpName:s} = {html.escape(repr(dep.obj.val))} {dep.obj._id:d}</td>"
                    else:
                        ir = f"<td port='i{node_in_i:d}'>{inpName:s}</td>"
                    input_rows.append(ir)

                    if not isInlinableConst and edgeRequired:
                        dep: Union[HlsNetNodeOut, HlsNetNodeOutLazy]
                        dst = f"{node.get_name():s}:i{node_in_i:d}"
                        attrs = {}
                        depTime = None
                        if isinstance(dep, HlsNetNodeOut):
                            depObj = dep.obj
                            if time is not None and depObj.scheduledOut:
                                depTime = depObj.scheduledOut[dep.out_i]

                            if expandAggregates and\
                                    isinstance(depObj, HlsNetNodeAggregate) and\
                                    depObj in self._expandedNodes:
                                # connect to output port node instead, because parent is represented as a pydot.Cluster
                                dep_node = self._node_from_HlsNetNode(depObj._outputsInside[dep.out_i])
                                src = f"{dep_node.get_name():s}:o0"
                            else:
                                dep_node = self._node_from_HlsNetNode(depObj)
                                src = f"{dep_node.get_name():s}:o{dep.out_i:d}"
                                if isinstance(depObj, HlsNetNodeIoClusterCore):
                                    if dep is depObj.inputNodePort:
                                        # swap src and dst for inputNodePort port of HlsNetNodeIoClusterCore which is output
                                        # but its meaning is input (to generate more acceptable visual appearance of graph)
                                        src, dst = dst, src
                                    attrs["shape"] = "none"
                        else:
                            dep_node = self._node_from_HlsNetNode(dep)
                            src = f"{dep_node.get_name():s}:o0"

                        if HdlType_isVoid(dep._dtype):
                            attrs["style"] = "dotted"

                        if time is not None and\
                                depTime is not None and\
                                depTime > time:
                            # reverse edge (but keep it visually in the same order) to keep ordering of nodes based on time
                            src, dst = dst, src
                            attrs["dir"] = "back"

                        e = pydot.Edge(src, dst, **attrs)
                        self.graph.add_edge(e)

                # add link from parent aggregate port
                if isinstance(obj, HlsNetNodeAggregatePortIn):
                    obj: HlsNetNodeAggregatePortIn

                    dep = obj.parentIn.obj.dependsOn[obj.parentIn.in_i]
                    depObj = dep.obj
                    if isinstance(depObj, HlsNetNodeAggregate):
                        depNode = depObj._outputsInside[dep.out_i]
                        dep_node = self._node_from_HlsNetNode(depNode)
                        src = f"{dep_node.get_name():s}:o0"
                    else:
                        dep_node = self._node_from_HlsNetNode(depObj)
                        src = f"{dep_node.get_name():s}:o{dep.out_i:d}"
                    attrs = {}
                    if HdlType_isVoid(dep._dtype):
                        attrs["style"] = "dotted"

                    dst = f"{node.get_name():s}:i0"
                    e = pydot.Edge(src, dst, **attrs)
                    self.graph.add_edge(e)

                for shadow_dst, isExplicitBackedge in obj.debugIterShadowConnectionDst():
                    if isinstance(shadow_dst, HlsNetNode) and shadow_dst not in self.allNodes:
                        continue
                    shadow_dst_node = self._node_from_HlsNetNode(shadow_dst)
                    src = f"{node.get_name():s}"
                    dst = f"{shadow_dst_node.get_name():s}"
                    extraAttrs = {}
                    if isExplicitBackedge or (
                            obj.scheduledZero is not None and
                            shadow_dst.scheduledZero is not None and
                            obj.scheduledZero > shadow_dst.scheduledZero):
                        # reverse edge (but keep it visually in the same order) to keep ordering of nodes based on time
                        src, dst = dst, src
                        extraAttrs["dir"] = "back"

                    e = pydot.Edge(src, dst, style="dashed", color="gray", **extraAttrs)
                    self.graph.add_edge(e)

            except Exception as e:
                raise AssertionError("defective node", obj)
        else:
            assert isinstance(obj, HlsNetNodeOutLazy), obj

        output_rows = []
        if isinstance(obj, HlsNetNode):
            scheduledOut = obj.scheduledOut
            clkPeriod = obj.netlist.normalizedClkPeriod
            if scheduledOut is None:
                scheduledOut = (None for _ in obj._outputs)
            for node_out_i, (out, time) in enumerate(zip(obj._outputs, scheduledOut)):
                if out.name is not None:
                    outName = out.name
                else:
                    outName = f"o{node_out_i:d}"
                if time is not None:
                    outName = f"{outName} {self._formatScheduleTime(time, clkPeriod)}"

                output_rows.append(f"<td port='o{node_out_i:d}'>{outName:s}</td>")
            if isinstance(obj, HlsNetNodeAggregatePortOut):
                assert not obj._outputs, obj
                output_rows.append(f"<td port='o0'></td>")

        else:
            output_rows.append("<td port='o0'>o0</td>")

        buff = []

        buff.append(f'''<
        <table bgcolor="{bgcolor:s}" border="0" cellborder="1" cellspacing="0">\n''')

        if isinstance(obj, HlsNetNodeConst):
            label = f"{obj.val} id:{obj._id:d}"
        elif isinstance(obj, HlsNetNodeOperator):
            if obj.operator in COMPARE_OPS:
                dep = obj.dependsOn[0]
                if dep is None:
                    t = "<INVALID>"
                else:
                    t = obj.dependsOn[0]._dtype
            else:
                t = obj._outputs[0]._dtype
            name = ""
            if obj.name is not None:
                name = f" \"{html.escape(obj.name)}\""
            label = f"{obj.operator.id if isinstance(obj.operator, OpDefinition) else str(obj.operator)} {obj._id:d} {self._formatNodeScheduleTime(obj)}{name:s} {t}"
        elif isinstance(obj, (HlsNetNodeRead, HlsNetNodeWrite, HlsNetNodeLoopStatus)):
            label = f"{_reprMinify(obj):s}{self._formatNodeScheduleTime(obj)}"
        elif isinstance(obj, HlsNetNodeAggregatePortIn):
            label = (f"{obj.__class__.__name__} {obj._id:d} ({obj.parentIn.obj._id:d}:i{obj.parentIn.in_i})"
            f" {self._formatNodeScheduleTime(obj)}\"{html.escape(obj.name) if obj.name else '':s}\"")
        elif isinstance(obj, HlsNetNodeAggregatePortOut):
            label = (f"{obj.__class__.__name__} {obj._id:d} ({obj.parentOut.obj._id:d}:o{obj.parentOut.out_i})"
            f" {self._formatNodeScheduleTime(obj)}\"{html.escape(obj.name) if obj.name else '':s}\"")
        elif obj.name is not None:
            label = f"{obj.__class__.__name__} {obj._id:d} {self._formatNodeScheduleTime(obj)}\"{html.escape(obj.name):s}\""
        else:
            label = f"{obj.__class__.__name__} {obj._id:d}{self._formatNodeScheduleTime(obj)}"

        buff.append(f'            <tr><td colspan="2">{html.escape(label):s}</td></tr>\n')
        if isinstance(obj, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)):
            if obj._loopChannelGroup is not None:
                buff.append(f'            <tr><td colspan="2">{html.escape(repr(obj._loopChannelGroup))}</td></tr>\n')

            if isinstance(obj, HlsNetNodeWriteBackedge):
                obj: HlsNetNodeWriteBackedge
                if obj.channelInitValues:
                    buff.append(f'            <tr><td colspan="2">init:{html.escape(repr(obj.channelInitValues)):s}</td></tr>\n')

        # if useInputConstRow:
        #    assert len(constInputRows) == len(input_rows)
        #    for c, i, o in zip_longest(constInputRows, input_rows, output_rows, fillvalue="<td></td>"):
        #        buff.append(f"            <tr>{i:s}{c:s}{o:s}</tr>\n")
        # else:
        for i, o in zip_longest(input_rows, output_rows, fillvalue="<td></td>"):
            buff.append(f"            <tr>{i:s}{o:s}</tr>\n")
        buff.append('        </table>>')

        node.set("label", "".join(buff))
        return node

    def dumps(self):
        return self.graph.to_string()


class HlsNetlistPassDumpNodesDot(HlsNetlistPass):

    def __init__(self, outStreamGetter: OutputStreamGetter, expandAggregates: bool=True,
                 addLegend:bool=True, showVoid:bool=True):
        self.outStreamGetter = outStreamGetter
        self.expandAggregates = expandAggregates
        self.addLegend = addLegend
        self.showVoid = showVoid

    def _getNodes(self, netlist: HlsNetlistCtx):
        if self.expandAggregates:
            nodeIt = netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER)
        else:
            nodeIt = netlist.iterAllNodes()
        if self.showVoid:
            yield from nodeIt
        else:
            for n in nodeIt:
                if isinstance(n, HlsNetNodeIoClusterCore):
                    continue
                elif isinstance(n, HlsNetNodeDelayClkTick) and HdlType_isVoid(n._outputs[0]._dtype):
                    continue
                elif isinstance(n, HlsNetNodeAggregatePortIn):
                    if HdlType_isVoid(n._outputs[0]._dtype):
                        continue
                elif isinstance(n, HlsNetNodeAggregatePortOut):
                    if HdlType_isVoid(n.parentOut._dtype):
                        continue
                elif isinstance(n, HlsNetNodeOperator) and n.operator is AllOps.CONCAT and HdlType_isVoid(n._outputs[0]._dtype):
                    continue

                yield n

    def _edgeFilterVoid(self, src: HlsNetNodeOut, dst: HlsNetNodeOut):
        return not HdlType_isVoid(src._dtype)

    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphwiz = HwtHlsNetlistToGraphwiz(name, self._getNodes(netlist), self.expandAggregates, self.addLegend)
            if not self.showVoid:
                toGraphwiz._edgeFilterFn = self._edgeFilterVoid
            toGraphwiz.construct()
            out.write(toGraphwiz.dumps())
        finally:
            if doClose:
                out.close()


class HlsNetlistPassDumpIoClustersDot(HlsNetlistPassDumpNodesDot):

    def __init__(self, outStreamGetter:OutputStreamGetter, expandAggregates: bool=False, addLegend:bool=True):
        HlsNetlistPassDumpNodesDot.__init__(self, outStreamGetter, expandAggregates=expandAggregates, addLegend=addLegend)
        self._edgeFilterFn = self._edgeFilter

    def _edgeFilter(self, src: HlsNetNodeOut, dst: HlsNetNodeOut):
        return HdlType_isVoid(src._dtype)

    def getNodes(self, netlist: HlsNetlistCtx):
        return (n for n in super(HlsNetlistPassDumpIoClustersDot, self).getNodes(netlist)
                 if isinstance(n, (HlsNetNodeExplicitSync, HlsNetNodeIoClusterCore))
                   or (isinstance(n, HlsNetNodeOperator) and n.operator is AllOps.CONCAT and HdlType_isVoid(n._outputs[0]._dtype)))

