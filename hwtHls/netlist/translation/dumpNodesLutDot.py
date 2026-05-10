import pydot
from typing import Union

from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.techmap.techmap import HlsNetNode as HlsNetNodeCpp, PoolOfHlsNetNode
from hwtHls.netlist.translation.dumpNodesDot import HwtHlsNetlistToGraphviz
from hwtHls.netlist.scheduler.clk_math import SchedTime_format


class HwtHlsNetlistLutToGraphviz():
    """
    Variant of :class:`HwtHlsNetlistToGraphviz` for LUT graph. (gate node is node mapped in LUT).
    In LUT graph the gate nodes may appear in multiple LUT nodes.
    """

    def __init__(self, name:str, lutNodes:list[HlsNetNodeCpp], lutGates: dict[HlsNetNodeCpp, PoolOfHlsNetNode],
                 cppNodeToPyNode: dict[HlsNetNodeCpp, HlsNetNode],
                 colorOverride:dict[HlsNetNode, Union[str, tuple[str, str]]]={}):
        self.lutNodes = lutNodes
        self.lutGates = lutGates
        self.cppNodeToPyNode = cppNodeToPyNode
        self.graph = pydot.Dot(f'"{name}"')
        self.graph.set("rankdir", "LR")
        self.toDotMap: dict[tuple[HlsNetNodeCpp, HlsNetNode], pydot.Node] = {}
        self.nodeCounter = 0
        self._colorOverride = colorOverride

    def _getNewNodeId(self):
        i = self.nodeCounter
        self.nodeCounter += 1
        return i

    def dumps(self):
        return self.graph.to_string()

    def construct(self):
        graph = self.graph
        lutGates = self.lutGates
        cppNodeToPyNode = self.cppNodeToPyNode
        toDotMap = self.toDotMap
        # construct nodes
        for lutNodeCpp in self.lutNodes:
            lutClusterId = f"n{self._getNewNodeId()}"
            lutDotCluster = pydot.Cluster(lutClusterId, label=f'"LUT {lutNodeCpp._id:d}"')
            graph.add_subgraph(lutDotCluster)
            toDotMap[lutNodeCpp] = lutDotCluster
            try:
                _lutGates: PoolOfHlsNetNode = lutGates[lutNodeCpp]
            except KeyError:
                # case for PI/PO which is not part of any LUT
                _lutGates = (lutNodeCpp,)
            for lutGateNodeCpp in _lutGates:
                lutGateNodePy = cppNodeToPyNode[lutGateNodeCpp]
                bgcolor, color = HwtHlsNetlistToGraphviz._getColor(self, lutGateNodePy)
                lutGateNodeDot = pydot.Node(f"n{self._getNewNodeId()}", style="filled", fillcolor=bgcolor, color=bgcolor)
                if lutGateNodeCpp.scheduledZero is not None:
                    normalizedClkPeriod = lutNodeCpp.netlist.normalizedClkPeriod
                    t = SchedTime_format(lutGateNodeCpp.scheduledZero, normalizedClkPeriod)
                    label = f'"{lutGateNodeCpp._id:d} {t:s}"'
                else:
                    label = f'"{lutGateNodeCpp._id:d}"'

                lutGateNodeDot.set("label", label)
                lutDotCluster.add_node(lutGateNodeDot)
                toDotMap[(lutNodeCpp, lutGateNodeCpp)] = lutGateNodeDot

        # construct edes between nodes
        for lutNodeCpp in self.lutNodes:
            lutNodeCpp: HlsNetNodeCpp
            lutDotCluster = toDotMap[lutNodeCpp]
            try:
                _lutGates: PoolOfHlsNetNode = lutGates[lutNodeCpp]
            except KeyError:
                # case for PI/PO which is not part of any LUT
                _lutGates = (lutNodeCpp,)

            for lutGateNodeCpp in _lutGates:
                lutGateNodeCpp: HlsNetNodeCpp
                dst: pydot.Node = toDotMap[(lutNodeCpp, lutGateNodeCpp)]
                for dep in lutGateNodeCpp.iterInDepNodes():
                    if dep in _lutGates:
                        src: pydot.Node = toDotMap[(lutNodeCpp, dep)]
                        e = pydot.Edge(src.get_name(), dst.get_name())
                        lutDotCluster.add_edge(e)
                    else:
                        try:
                            src: pydot.Node = toDotMap[(dep, dep)]
                        except KeyError:
                            # this is a primary input, we need to construct its node at top level
                            piNodePy = cppNodeToPyNode[dep]
                            bgcolor, color = HwtHlsNetlistToGraphviz._getColor(self, piNodePy)
                            piNode = pydot.Node(f"n{self._getNewNodeId()}", style="filled", fillcolor=bgcolor, color=bgcolor)
                            if dep.scheduledZero is not None:
                                normalizedClkPeriod = dep.netlist.normalizedClkPeriod
                                t = SchedTime_format(dep.scheduledZero, normalizedClkPeriod)
                                label = f'"PI {piNodePy._id:d} {piNodePy.name} {t}"'
                            else:
                                label = f'"PI {piNodePy._id:d} {piNodePy.name}"'

                            piNode.set("label", label)
                            graph.add_node(piNode)
                            src = toDotMap[(dep, dep)] = piNode
                        e = pydot.Edge(src.get_name(), dst.get_name())
                        graph.add_edge(e)

