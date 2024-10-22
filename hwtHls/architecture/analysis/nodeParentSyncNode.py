from typing import Tuple # Dict, Sequence, 

#from hwt.pyUtils.typingFuture import override
#from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
#from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
#from hwtHls.netlist.nodes.node import HlsNetNode

ArchSyncNodeTy = Tuple[ArchElement, int]
#
# :attention: This was removed because its maintenance was bigger performance hit than gain from faster lookup 
#class HlsAndRtlNetlistAnalysisPassNodeParentSyncNode(HlsArchAnalysisPass):
#    """
#    An analysis which provides dictionary for fast lookup of hierarchy path for each HlsNetNode in hierarchy of ArchSyncNodes
#    
#    """
#
#    def __init__(self):
#        super(HlsAndRtlNetlistAnalysisPassNodeParentSyncNode, self).__init__()
#        self.nodePath: Dict[HlsNetNode, ArchSyncNodeTy] = {}
#
#    def _collectHierarchyNodes(self, archElements: Sequence[ArchElement]):
#        nodePath = self.nodePath
#        for elm in archElements:
#            assert isinstance(elm, ArchElement), elm
#
#            for clkI, nodes in elm.iterStages():
#                syncNode: ArchSyncNodeTy = (elm, clkI)
#
#                for n in nodes:
#                    nodePath[n] = syncNode
#
#    def addNode(self, n: HlsNetNode, syncNode: ArchSyncNodeTy):
#        assert not n._isMarkedRemoved
#        assert n not in self.nodePath
#        self.nodePath[n] = syncNode
#
#    def removeNode(self, n: HlsNetNode):
#        v = self.nodePath.pop(n, None)
#        assert v is not None, ("Node was not previously tracked", n)
#
#    def moveNode(self, n: HlsNetNode, newSyncNode: ArchSyncNodeTy):
#        assert not n._isMarkedRemoved, n
#        v = self.nodePath.pop(n, None)
#        assert v is not None, ("Node was not previously tracked", n)
#        self.nodePath[n] = newSyncNode
#
#    @override
#    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
#        assert not self.nodePath
#        self._collectHierarchyNodes(netlist.iterAllNodes())
