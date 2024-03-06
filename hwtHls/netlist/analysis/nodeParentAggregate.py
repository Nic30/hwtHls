from typing import Tuple, Dict

from hwt.pyUtils.uniqList import UniqList
from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass
from hwtHls.netlist.nodes.aggregate import HlsNetNodeAggregate
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.node import HlsNetNode


HlsNetlistHierarchyPath = Tuple[HlsNetNodeAggregate, ...]


class HlsNetlistAnalysisPassNodeParentAggregate(HlsNetlistAnalysisPass):
    """
    An analysis which provides dictionaries for fast lookup of hierarchy path for each node
    """

    def __init__(self, netlist:"HlsNetlistCtx"):
        HlsNetlistAnalysisPass.__init__(self, netlist)
        self.nodeHieararchy: Dict[HlsNetlistHierarchyPath, UniqList[HlsNetNode]] = {}
        self.nodePath: Dict[HlsNetNode, HlsNetlistHierarchyPath] = {}

    def getBottomMostArchElementParent(self, n: HlsNetNode):
        nPath = self.nodePath[n]
        for parent in reversed(nPath):
            if isinstance(parent, ArchElement):
                return parent

        raise ValueError("Node has no ArchElement parent", n)

    def _collectHierarchyNodes(self, currentPath: HlsNetlistHierarchyPath, nodes: UniqList[HlsNetNode]):
        self.nodeHieararchy[currentPath] = nodes
        for n in nodes:
            self.nodePath[n] = currentPath
            if isinstance(n, HlsNetNodeAggregate):
                self._collectHierarchyNodes(tuple((*currentPath, n)), n._subNodes)

    def run(self):
        assert not self.nodeHieararchy
        assert not self.nodePath
        self._collectHierarchyNodes((), UniqList(self.netlist.iterAllNodes()))
