from enum import Enum
import html
from itertools import zip_longest
import pydot
from typing import List, Union, Dict, Optional, Callable, Tuple

from hwt.hdl.operatorDefs import COMPARE_OPS, HwtOps, HOperatorDef
from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.hdlTypeVoid import HdlType_isVoid
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregatePortOut, \
    HlsNetNodeAggregatePortIn, HlsNetNodeAggregate
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.const import HlsNetNodeConst
from hwtHls.netlist.nodes.delay import HlsNetNodeDelayClkTick
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.fsmStateEn import HlsNetNodeFsmStateEn, \
    HlsNetNodeStageAck
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
from hwtHls.netlist.scheduler.clk_math import indexOfClkPeriod, \
    offsetInClockCycle, timeUntilClkEnd
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.netlist.nodes.fsmStateWrite import HlsNetNodeFsmStateWrite


COLOR_INPUT_READ = "LightGreen"
COLOR_OUTPUT_WRITE = "LightBlue"
COLOR_SYNC_INTERNAL = "Chartreuse"  # bright type of green
COLOR_SPECIAL_PURPOSE = "MediumSpringGreen"
COLOR_TEMPORARY_NODE = "LightCoral"


class ClockWindowLayer(Enum):
    IN = 0
    # BODY = 1 # body is replresented by original (elm, clkI) tuple
    OUT = 2


class HwtHlsNetlistToGraphviz():
    """
    Generate a Graphviz (dot) diagram of the netlist.
    """
    # ORDERING_EDGE_STYLE = { "color": "red"}
    # ORDERING_NODE_STYLE = {}
    ORDERING_EDGE_STYLE = {"style": "invis"}  # , "weight": 1
    ORDERING_NODE_STYLE = {"shape": "point", "penwidth":"0", "color":"white"}

    def __init__(self, name: str, nodes: List[HlsNetNode],
                 expandAggregates: bool,
                 addLegend: bool,
                 addOrderingNodes: bool,
                 showArchElementLinks:bool=True,
                 colorOverride:Dict[HlsNetNode, Union[str, Tuple[str, str]]]={}):
        """
        :attention: if expandAggregates==True the nodes should contain also parent aggregates
            and parent aggregate position in nodes list must be before its children.
            
        :param showArchElementLinks: if True add links between HlsNetNodeAggregatePortIn/HlsNetNodeAggregatePortOut
            instances, else keep just the dst/src name in port node
        """
        self.name = name
        self.allNodes = SetList(nodes)
        self.graph = pydot.Dot(f'"{name}"')
        self.obj_to_node: Dict[HlsNetNode, pydot.Node] = {}
        self.nodeCounter = 0
        self.expandAggregates = expandAggregates
        self.addLegend = addLegend
        self.addOrderingNodes = addOrderingNodes
        self._edgeFilterFn: Optional[Callable[[HlsNetNodeOut, HlsNetNodeIn], bool]] = None
        self._parentCluster: Dict[Union[HlsNetNodeAggregate,
                                        Tuple[HlsNetNodeAggregate, int],
                                        Tuple[HlsNetNodeAggregate, int, ClockWindowLayer]], pydot.Cluster] = {}
        self._parentOfNode: Dict[HlsNetNode, Tuple[HlsNetNodeAggregate, int]] = {}
        self._showArchElementLinks = showArchElementLinks
        self._colorOverride = colorOverride

    def _constructLegend(self):
        legendTable = f"""<
<table border="0" cellborder="1" cellspacing="0">
  <tr><td bgcolor="{COLOR_INPUT_READ:s}">HlsNetNodeRead, HlsNetNodeReadSync</td></tr>
  <tr><td bgcolor="{COLOR_OUTPUT_WRITE:s}">HlsNetNodeWrite</td></tr>
  <tr><td bgcolor="plum">HlsNetNodeConst</td></tr>
  <tr><td bgcolor="{COLOR_SYNC_INTERNAL:s}">HlsNetNodeExplicitSync</td></tr>
  <tr><td bgcolor="{COLOR_SPECIAL_PURPOSE:s}">HlsNetNodeLoopStatus, HlsProgramStarter, HlsNetNodeFsmStateEn, HlsNetNodeStageAck, HlsNetNodeFsmStateWrite</td></tr>
  <tr><td bgcolor="gray">shadow connection</td></tr>
  <tr><td bgcolor="{COLOR_TEMPORARY_NODE:s}">HlsNetNodeOutLazy</td></tr>
  <tr><td bgcolor="gray">HlsNetNodeAggregatePortIn/Out</td></tr>
</table>>"""
        return pydot.Node("legend", label=legendTable, style='filled', shape="plain")

    def _getColor(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        color = "black"
        bgcolor = "white"
        c = self._colorOverride.get(obj)
        if c is not None:
            if isinstance(c, str):
                return (c, bgcolor)
            else:
                assert isinstance(c, tuple) and len(c) == 2 and isinstance(c[0], str) and isinstance(c[1], str)
                return c

        if isinstance(obj, HlsNetNodeOutLazy):
            bgcolor = COLOR_TEMPORARY_NODE
        elif isinstance(obj, (HlsNetNodeRead, HlsNetNodeReadSync)):
            bgcolor = COLOR_INPUT_READ
        elif isinstance(obj, HlsNetNodeWrite):
            bgcolor = COLOR_OUTPUT_WRITE
        elif isinstance(obj, HlsNetNodeConst):
            bgcolor = "plum"
        elif isinstance(obj, HlsNetNodeExplicitSync):
            bgcolor = COLOR_SYNC_INTERNAL
        elif isinstance(obj, (HlsNetNodeLoopStatus, HlsProgramStarter, HlsNetNodeFsmStateEn, HlsNetNodeStageAck, HlsNetNodeFsmStateWrite)):
            bgcolor = COLOR_SPECIAL_PURPOSE
        elif isinstance(obj, (HlsNetNodeAggregatePortIn, HlsNetNodeAggregatePortOut)):
            color = "gray"

        return bgcolor, color

    def _getNewNodeId(self):
        i = self.nodeCounter
        self.nodeCounter += 1
        return i

    def _getEdgeWeight(self, timeDiff:SchedTime, clkPeriod:SchedTime):
        """
        :note: longer edge = smaller weight, max weight for 0 (=clkPeriod)
        """
        timeDiff = abs(timeDiff)
        if timeDiff < clkPeriod:
            # timeDiff=0         -> clkPeriod
            # timeDiff=clkPeriod -> 1
            return clkPeriod + 1 - timeDiff
        else:
            return clkPeriod / abs(timeDiff)

    def _constructNodeHierarchy(self):
        assert self.expandAggregates
        allNodes = self.allNodes
        parentOfNode = self._parentOfNode
        parentCluster = self._parentCluster
        addOrderingNodes = self.addOrderingNodes
        for parent in allNodes:
            if isinstance(parent, HlsNetNodeAggregate):
                parent: HlsNetNodeAggregate
                label = f"{parent.__class__.__name__} {parent._id:d} {self._formatNodeScheduleTime(parent)}{' ' + parent.name if parent.name else ''}"
                elmClusterName = f"n{self._getNewNodeId()}"
                clusterNode = pydot.Cluster(elmClusterName, label=f'"{html.escape(label)}"')
                g, ordringIn, orderingOut = self._getGraph(parent)
                g.add_subgraph(clusterNode)
                parentCluster[parent] = (clusterNode, None, None)

                for n in parent.subNodes:
                    if n in parentOfNode:
                        continue
                    assert n not in parentOfNode, ("Each node is supposed to have just a single parent", n,
                                                   "prev found:", parentOfNode[n], "now found in:", parent, "expected from node", n.parent)
                    parentOfNode[n] = parent

                if isinstance(parent, ArchElement) and parent.scheduledZero is not None:
                    # parentOfNode nodes are already preset in the case that there
                    # are some nodes which are not placed in clock windows yet
                    parent: ArchElement
                    prevOrderingNodeId: Optional[str] = ordringIn

                    orderingEdgeStyle = self.ORDERING_EDGE_STYLE
                    orderingNodeStyle = self.ORDERING_NODE_STYLE
                    clkPeriod = parent.netlist.normalizedClkPeriod
                    weithFor0ClkPeriodLongEdge = self._getEdgeWeight(0, clkPeriod)
                    weithFor1ClkPeriodLongEdge = self._getEdgeWeight(clkPeriod, clkPeriod)
                    for clkI, nodes in parent.iterStages():
                        if not nodes:
                            continue
                        label = f"{clkI}"
                        stageClusterId = f"{elmClusterName:s}_{clkI:d}"
                        clockWindowClusterNode = pydot.Cluster(stageClusterId, label=f'"{html.escape(label)}"')
                        clusterNode.add_subgraph(clockWindowClusterNode)
                        if addOrderingNodes:
                            # divide nodes to 3 layers to have nice ordering of nodes and clock window clusters them self
                            # clockWindowClusterNodeIn = pydot.Cluster(f"{stageClusterId}_in")
                            # clockWindowClusterNode.add_subgraph(clockWindowClusterNodeIn)
                            #
                            # clockWindowClusterNodeBody = pydot.Cluster(f"{stageClusterId}_body")
                            # clockWindowClusterNode.add_subgraph(clockWindowClusterNodeBody)
                            #
                            # clockWindowClusterNodeOut = pydot.Cluster(f"{stageClusterId}_out")
                            # clockWindowClusterNode.add_subgraph(clockWindowClusterNodeOut)

                            orderingInNode = pydot.Node(f"{stageClusterId:s}_orderingIn", **orderingNodeStyle)
                            clockWindowClusterNode.add_node(orderingInNode)

                            # clockWindowClusterNodeIn.add_node(orderingInNode)
                            if prevOrderingNodeId is not None:
                                e = pydot.Edge(prevOrderingNodeId, orderingInNode.get_name(), weight=weithFor0ClkPeriodLongEdge, **orderingEdgeStyle)
                                clusterNode.add_edge(e)

                            # orderingBodyNode = pydot.Node(f"{stageClusterId:s}_orderingBody", **orderingNodeStyle)
                            # clockWindowClusterNodeBody.add_node(orderingBodyNode)
                            # e = pydot.Edge(orderingInNode.get_name(), orderingBodyNode.get_name(), **orderingEdgeStyle)
                            # clockWindowClusterNode.add_edge(e)

                            orderingOutNode = pydot.Node(f"{stageClusterId:s}_orderingOut", **orderingNodeStyle)
                            # clockWindowClusterNodeOut.add_node(orderingOutNode)
                            # e = pydot.Edge(orderingBodyNode.get_name(), orderingOutNode.get_name(), **orderingEdgeStyle)
                            clockWindowClusterNode.add_node(orderingOutNode)
                            e = pydot.Edge(orderingInNode.get_name(), orderingOutNode.get_name(), weight=weithFor1ClkPeriodLongEdge, **orderingEdgeStyle)
                            clockWindowClusterNode.add_edge(e)

                            # parentCluster[(parent, clkI, ClockWindowLayer.IN)] = clockWindowClusterNodeIn
                            # parentCluster[(parent, clkI)] = clockWindowClusterNodeBody
                            # parentCluster[(parent, clkI, ClockWindowLayer.OUT)] = clockWindowClusterNodeOut
                            orderingInNodeId = orderingInNode.get_name()
                            orderingOutNodeId = orderingOutNode.get_name()
                        else:
                            orderingInNodeId = None
                            orderingOutNodeId = None

                        parentCluster[(parent, clkI)] = (clockWindowClusterNode, orderingInNodeId, orderingOutNodeId)

                        for n in nodes:
                            # if node has no predecessors in this window add it to input cluster
                            # if node has no successor in this window add it to output cluster
                            # else add it to body
                            parentOfNode[n] = (parent, clkI)
                        prevOrderingNodeId = orderingOutNodeId

    def construct(self):
        expandAggregates = self.expandAggregates
        if expandAggregates:
            self._constructNodeHierarchy()
        for n in self.allNodes:
            if expandAggregates and n in self._parentCluster:
                continue
            if isinstance(n, HlsNetNodeConst) and len(n.usedBy[0]) == 1:
                continue  # const inlined into user node
            self._node_from_HlsNetNode(n)

        # if self.allNodes and self.allNodes[0].scheduledZero is not None:
        #    # add invisible edges for IO nodes to assert visual order corresponds to a schedule time
        #    if expandAggregates:
        #        nodesPerParent = {}
        #        for n in self.allNodes:
        #
        #    else:
        #        raise NotImplementedError()

        if self.addLegend:
            self.graph.add_node(self._constructLegend())

    def _getGraph(self, n: HlsNetNode) -> Union[Tuple[pydot.Graph, None, None],
                                                Tuple[pydot.Cluster, str, str]]:
        """
        :note: strings in return tuple represents ids of orderingIn, orderingOut node
        """
        if self.expandAggregates:
            parent = self._parentOfNode.get(n, None)
            if parent is None:
                return self.graph, None, None
            else:
                return self._parentCluster[parent]
        else:
            return self.graph, None, None

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
            if isinstance(node, HlsNetNodeAggregatePortIn):
                outerTime = node.parent.scheduledIn[node.parentIn.in_i]
            elif isinstance(node, HlsNetNodeAggregatePortOut):
                outerTime = node.parent.scheduledOut[node.parentOut.out_i]
            else:
                outerTime = None

            if outerTime is not None and t != outerTime:
                return f"{cls._formatScheduleTime(t, clkPeriod)} (outside:{cls._formatScheduleTime(outerTime, clkPeriod)})"
            return cls._formatScheduleTime(t, clkPeriod)

    def _node_from_HlsNetNode_input(self,
                                    g: Union[pydot.Node, pydot.Cluster],
                                    node: pydot.Node,
                                    clkPeriod: SchedTime,
                                    clkI: int,
                                    inp: HlsNetNodeIn,
                                    node_in_i: int, dep: Union[HlsNetNodeOut, HlsNetNodeOutLazy, None],
                                    time: Optional[SchedTime]):
        edgeFilter = self._edgeFilterFn
        expandAggregates = self.expandAggregates
        if inp.name is not None:
            inpName = inp.name
        else:
            inpName = f"i{node_in_i:d}"
        if time is not None:
            inpName = f"{inpName} {self._formatScheduleTime(time, clkPeriod)}"
        isInlinableConst = isinstance(dep, HlsNetNodeOut) and \
                           isinstance(dep.obj, HlsNetNodeConst) and\
                           len(dep.obj.usedBy) == 1
        edgeRequired = dep is not None and (edgeFilter is None or edgeFilter(dep, inp))
        if edgeRequired and isInlinableConst:
            ir = f"<td port='i{node_in_i:d}'>{inpName:s} = {html.escape(repr(dep.obj.val))} {dep.obj._id:d}</td>"
        else:
            ir = f"<td port='i{node_in_i:d}'>{inpName:s}</td>"
        hasPredecessorInThisClkWindow = False
        if not isInlinableConst and edgeRequired:
            dep: Union[HlsNetNodeOut, HlsNetNodeOutLazy]
            dst = f"{node.get_name():s}:i{node_in_i:d}"
            attrs = {}
            depTime = None
            isInSameElm = False
            isInSameElmClkWindow = False
            if isinstance(dep, HlsNetNodeOut):
                depObj = dep.obj
                if time is not None and depObj.scheduledOut:
                    depTime = depObj.scheduledOut[dep.out_i]

                if expandAggregates and\
                   isinstance(depObj, HlsNetNodeAggregate) and\
                   depObj in self._parentCluster:
                    # connect to output port node instead, because parent is represented as a pydot.Cluster
                    dep_node = self._node_from_HlsNetNode(depObj._outputsInside[dep.out_i])
                    src = f"{dep_node.get_name():s}:o0"
                else:
                    dep_node = self._node_from_HlsNetNode(depObj)
                    src = f"{dep_node.get_name():s}:o{dep.out_i:d}"
                    if time is not None and inp.obj.parent is depObj.parent:
                        isInSameElm = True
                        if dep.obj.scheduledOut is not None and\
                           time // clkPeriod == dep.obj.scheduledOut[dep.out_i] // clkPeriod:
                            isInSameElmClkWindow = True

                if clkI is not None and dep.obj.scheduledOut is not None and\
                   dep.obj.scheduledOut[dep.out_i] // clkPeriod == clkI:
                    hasPredecessorInThisClkWindow = True
            else:
                dep_node = self._node_from_HlsNetNode(dep)
                src = f"{dep_node.get_name():s}:o0"
            if HdlType_isVoid(dep._dtype):
                attrs["style"] = "dotted"
            if time is not None and depTime is not None:
                if depTime > time:
                    # reverse edge (but keep it visually in the same order) to keep ordering of nodes based on time
                    src, dst = dst, src
                    attrs["dir"] = "back"
                attrs["weight"] = self._getEdgeWeight(depTime - time, clkPeriod)
            e = pydot.Edge(src, dst, **attrs)

            if g is not self.graph:
                # try to put edge in lowest hierarchy parent possible
                if isInSameElmClkWindow:
                    g.add_edge(e)
                elif isInSameElm:
                    self._parentCluster[inp.obj.parent][0].add_edge(e)
                else:
                    self.graph.add_edge(e)
            else:
                self.graph.add_edge(e)

        return ir, hasPredecessorInThisClkWindow

    def _node_from_HlsNetNode_debugShadowConnections(self, clkPeriod: int, obj: HlsNetNode, node: pydot.Node):
        # construct edges for shadow connections
        for shadow_dst, isExplicitBackedge in obj.debugIterShadowConnectionDst():
            if isinstance(shadow_dst, HlsNetNode) and shadow_dst not in self.allNodes:
                continue
            shadow_dst_node = self._node_from_HlsNetNode(shadow_dst)
            src = f"{node.get_name():s}"
            dst = f"{shadow_dst_node.get_name():s}"
            attrs = {}
            hasSchedule = obj.scheduledZero is not None and shadow_dst.scheduledZero is not None
            if isExplicitBackedge or (hasSchedule and obj.scheduledZero > shadow_dst.scheduledZero):
                    # reverse edge (but keep it visually in the same order) to keep ordering of nodes based on time
                    src, dst = dst, src
                    attrs["dir"] = "back"
            if hasSchedule:
                attrs["weigh"] = self._getEdgeWeight(obj.scheduledZero - shadow_dst.scheduledZero, clkPeriod)
            # if it is edge crossing time windows exclude it from ordering of the graph
            # because stage clusters already have ordering edges
            # if obj.scheduledZero is not None and shadow_dst.scheduledZero is not None:
            #    if obj.scheduledZero // clkPeriod != shadow_dst.scheduledZero // clkPeriod:
            #        # attrs["weight"] = 0
            #        attrs["constraint"] = False

            e = pydot.Edge(src, dst, style="dashed", color="gray", **attrs)
            self.graph.add_edge(e)

    def _node_from_HlsNetNode_linkAggregatePortIn(self, obj: HlsNetNodeAggregatePortIn, node: pydot.Node, clkPeriod: SchedTime):
        parentIn = obj.parentIn
        dep = parentIn.obj.dependsOn[parentIn.in_i]
        if dep is None:
            inRow = f"<td port='i0'>{html.escape('<unconnected>'):s}</td>"
        else:
            inRow = f"<td port='i0'>{dep.obj._id}:o{dep.out_i}</td>"
        if dep is not None and self._showArchElementLinks or not isinstance(parentIn.obj, ArchElement):
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

            if obj.scheduledIn is not None:
                schedOut = dep.obj.scheduledOut
                if schedOut is not None:
                    attrs["weight"] = self._getEdgeWeight(obj.scheduledOut[0] - schedOut[dep.out_i], clkPeriod)

            dst = f"{node.get_name():s}:i0"
            e = pydot.Edge(src, dst, **attrs)
            self.graph.add_edge(e)
        return inRow

    def _node_from_HlsNetNode_outputs(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        # construct outputs
        output_rows = []
        hasUseInSameClkWindow = False
        if isinstance(obj, HlsNetNode):
            scheduledOut = obj.scheduledOut
            clkPeriod = obj.netlist.normalizedClkPeriod
            if scheduledOut is None:
                scheduledOut = (None for _ in obj._outputs)
                clkI = None
            else:
                clkI = obj.scheduledZero // clkPeriod

            for node_out_i, (out, uses, time) in enumerate(zip(obj._outputs, obj.usedBy, scheduledOut)):
                if out.name is not None:
                    outName = out.name
                else:
                    outName = f"o{node_out_i:d}"
                if time is not None:
                    outName = f"{outName} {self._formatScheduleTime(time, clkPeriod)}"
                    if not hasUseInSameClkWindow and clkI is not None:
                        for u in uses:
                            schedIn = u.obj.scheduledIn
                            if schedIn:
                                if schedIn[u.in_i] // clkPeriod == clkI:
                                    hasUseInSameClkWindow = True
                                    break
                output_rows.append(f"<td port='o{node_out_i:d}'>{outName:s}</td>")

            if isinstance(obj, HlsNetNodeAggregatePortOut):
                assert not obj._outputs, obj
                output_rows.append(f"<td port='o0'></td>")
        else:
            output_rows.append("<td port='o0'>o0</td>")

        return output_rows, hasUseInSameClkWindow

    def _node_from_HlsNetNode(self, obj: Union[HlsNetNode, HlsNetNodeOutLazy]):
        try:
            return self.obj_to_node[obj]
        except KeyError:
            pass
        g, orderingIn, orderingOut = self._getGraph(obj)
        # node needs to be constructed before connecting because graph may contain loops
        # fillcolor=color, style='filled',

        bgcolor, color = self._getColor(obj) if obj in self.allNodes else ("orange", "black")
        node = pydot.Node(f"n{self._getNewNodeId()}", shape="plaintext", bgcolor=bgcolor, color=color, fontcolor=color)
        g.add_node(node)
        self.obj_to_node[obj] = node

        # construct new node inputs and edges driving them
        input_rows = []
        if isinstance(obj, HlsNetNode):
            try:
                scheduledIn = obj.scheduledIn
                clkPeriod = obj.netlist.normalizedClkPeriod
                if scheduledIn is None:
                    scheduledIn = (None for _ in obj._inputs)
                    clkI = None
                else:
                    clkI = obj.scheduledZero // clkPeriod
                hasPredecessorInThisClkWindow = False
                for node_in_i, (inp, dep, time) in enumerate(zip(obj._inputs, obj.dependsOn, scheduledIn)):
                    if isinstance(dep, HlsNetNodeOut) and dep.obj not in self.allNodes:
                        # connected to something which is not part of selected graph
                        continue
                    inStr, _hasPredecessorInThisClkWindow = self._node_from_HlsNetNode_input(
                        g, node, clkPeriod, clkI, inp, node_in_i, dep, time)
                    input_rows.append(inStr)
                    if _hasPredecessorInThisClkWindow:
                        clkI = None  # disable checks for hasPredecessorInThisClkWindow
                        hasPredecessorInThisClkWindow = True

                if not hasPredecessorInThisClkWindow and obj.scheduledZero is not None and orderingIn is not None:
                    # add ordering edge to keep total cluster ordering in readable shape
                    e = pydot.Edge(orderingIn, node.get_name(), weight=self._getEdgeWeight(
                        offsetInClockCycle(obj.scheduledZero, clkPeriod), clkPeriod),
                        **self.ORDERING_EDGE_STYLE)
                    g.add_edge(e)

                # add link from parent aggregate port
                if isinstance(obj, HlsNetNodeAggregatePortIn):
                    inStr = self._node_from_HlsNetNode_linkAggregatePortIn(obj, node, clkPeriod)
                    input_rows.append(inStr)

                self._node_from_HlsNetNode_debugShadowConnections(clkPeriod, obj, node)

            except Exception as e:
                raise AssertionError("defective node", obj, e)
        else:
            assert isinstance(obj, HlsNetNodeOutLazy), obj

        output_rows, hasUseInSameClkWindow = self._node_from_HlsNetNode_outputs(obj)
        if not hasUseInSameClkWindow and orderingOut is not None:
            # add ordering edge to keep total cluster ordering in readable shape
            if obj.scheduledZero is None:
                weight = 1
            else:
                weight = self._getEdgeWeight(timeUntilClkEnd(obj.scheduledZero, clkPeriod), clkPeriod)
            e = pydot.Edge(node.get_name(), orderingOut, weight=weight, **self.ORDERING_EDGE_STYLE)
            g.add_edge(e)

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
            label = (f"{obj.operator.id if isinstance(obj.operator, HOperatorDef) else str(obj.operator)}"
                     f" {obj._id:d} {self._formatNodeScheduleTime(obj)}{name:s} {t}")
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
                if obj.associatedRead.channelInitValues:
                    initValuesStr = html.escape(repr(obj.associatedRead.channelInitValues))
                    buff.append(f'            <tr><td colspan="2">init:{initValuesStr:s}</td></tr>\n')

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


class HlsNetlistAnalysisPassDumpNodesDot(HlsNetlistAnalysisPass):
    """
    Dump nodes in graphviz dot format HwtHlsNetlistToGraphviz
    :see: :class:``
    """

    def __init__(self, outStreamGetter: OutputStreamGetter,
                 expandAggregates: bool=True,
                 addLegend:bool=True,
                 addOrderingNodes:bool=True,
                 showVoid:bool=True,
                 showArchElementLinks:bool=False,
                 colorOverride:Dict[HlsNetNode, Union[str, Tuple[str, str]]]={}):
        self.outStreamGetter = outStreamGetter
        self.expandAggregates = expandAggregates
        self.addLegend = addLegend
        self.addOrderingNodes = addOrderingNodes
        self.showVoid = showVoid
        self.showArchElementLinks = showArchElementLinks
        self.colorOverride = colorOverride

    def _getNodes(self, netlist: HlsNetlistCtx):
        if self.expandAggregates:
            nodeIt = netlist.iterAllNodesFlat(NODE_ITERATION_TYPE.PREORDER)
        else:
            nodeIt = netlist.iterAllNodes()
        if self.showVoid:
            yield from nodeIt
        else:
            for n in nodeIt:
                if isinstance(n, HlsNetNodeDelayClkTick) and HdlType_isVoid(n._outputs[0]._dtype):
                    continue
                elif isinstance(n, HlsNetNodeAggregatePortIn):
                    if HdlType_isVoid(n._outputs[0]._dtype):
                        continue
                elif isinstance(n, HlsNetNodeAggregatePortOut):
                    if HdlType_isVoid(n.parentOut._dtype):
                        continue
                elif isinstance(n, HlsNetNodeOperator) and n.operator is HwtOps.CONCAT and HdlType_isVoid(n._outputs[0]._dtype):
                    continue

                yield n

    def _edgeFilterVoid(self, src: HlsNetNodeOut, dst: HlsNetNodeOut):
        return not HdlType_isVoid(src._dtype)

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphviz = HwtHlsNetlistToGraphviz(
                name, self._getNodes(netlist), self.expandAggregates, self.addLegend, self.addOrderingNodes,
                showArchElementLinks=self.showArchElementLinks,
                colorOverride=self.colorOverride)
            if not self.showVoid:
                toGraphviz._edgeFilterFn = self._edgeFilterVoid
            toGraphviz.construct()
            out.write(toGraphviz.dumps())
        finally:
            if doClose:
                out.close()


class HlsNetlistAnalysisPassDumpIoClustersDot(HlsNetlistAnalysisPassDumpNodesDot):

    def __init__(self, outStreamGetter:OutputStreamGetter,
                 expandAggregates: bool=False,
                 addLegend:bool=True,
                 addOrderingNodes:bool=True,
                 colorOverride:Dict[HlsNetNode, Union[str, Tuple[str, str]]]={}):
        HlsNetlistAnalysisPassDumpNodesDot.__init__(self, outStreamGetter, expandAggregates=expandAggregates,
                                                    addLegend=addLegend,
                                                    addOrderingNodes=addOrderingNodes,
                                                    colorOverride=colorOverride)
        self._edgeFilterFn = self._edgeFilter

    def _edgeFilter(self, src: HlsNetNodeOut, dst: HlsNetNodeOut):
        return HdlType_isVoid(src._dtype)

    def getNodes(self, netlist: HlsNetlistCtx):
        return (n for n in super(HlsNetlistAnalysisPassDumpIoClustersDot, self).getNodes(netlist)
                 if isinstance(n, HlsNetNodeExplicitSync) or
                    (isinstance(n, HlsNetNodeOperator) and 
                     n.operator is HwtOps.CONCAT and
                     HdlType_isVoid(n._outputs[0]._dtype)))

