from typing import Tuple, Dict, Union, List, Sequence

from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchSyncNodeTy
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


ArchSyncNodeIoDict = Dict[ArchSyncNodeTy, Tuple[List[HlsNetNodeRead], List[HlsNetNodeWrite]]]
ArchSyncChannelToParentDict = Dict[Union[HlsNetNodeRead, HlsNetNodeWrite],
                                             ArchSyncNodeTy]


class HlsArchAnalysisPassChannelGraph(HlsArchAnalysisPass):
    """
    Collect graph of channels connecting ArchElement instances.
    The channel is represented by associated HlsNetNodeRead, HlsNetNodeWrite pairs
    The :class:`HlsNetNodeReadForwardedge`,
        :class:`HlsNetNodeWriteForwardedge`,
        :class:`HlsNetNodeReadBackedge` and
        :class:`HlsNetNodeWriteBackedge` instances are always associated.
    """

    def __init__(self):
        super(HlsArchAnalysisPassChannelGraph, self).__init__()
        self.ioNodeToParentSyncNode: ArchSyncChannelToParentDict = {}
        self.nodes: List[ArchSyncNodeTy] = []
        self.allChannelWrites: List[HlsNetNodeWrite] = []
        self.nodeIo: ArchSyncNodeIoDict = {}
        self.nodeChannels: ArchSyncNodeIoDict = {}

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        """
        Find all channels between ArchElements and build a simplified graph from them
        so we do not have to search for everything over and over in original netlist.
        """
        archElements: Sequence[ArchElement] = netlist.nodes

        ioNodeToParentSyncNode = self.ioNodeToParentSyncNode
        allChannelWrites = self.allChannelWrites
        allNodes = self.nodes
        nodeIo = self.nodeIo
        assert not ioNodeToParentSyncNode
        assert not allChannelWrites
        assert not allNodes
        assert not nodeIo

        for elm in archElements:
            assert isinstance(elm, ArchElement), elm

            for clkI, nodes in elm.iterStages():
                syncNode: ArchSyncNodeTy = (elm, clkI)
                allNodes.append(syncNode)
                inputList, outputList = nodeIo[syncNode] = ([], [])

                for n in nodes:
                    if isinstance(n, HlsNetNodeWrite):
                        ioNodeToParentSyncNode[n] = syncNode
                        if n.associatedRead is not None:
                            allChannelWrites.append(n)
                        else:
                            outputList.append(n)
                    elif isinstance(n, HlsNetNodeRead):
                        ioNodeToParentSyncNode[n] = syncNode
                        if n.associatedWrite is None:
                            inputList.append(n)

        nodeChannels = self.nodeChannels
        for n in allNodes:
            nodeChannels[n] = ([], [])

        for w in allChannelWrites:
            w: HlsNetNodeWrite
            srcNode = ioNodeToParentSyncNode[w]
            nodeChannels[srcNode][1].append(w)
            dstNode = ioNodeToParentSyncNode[w.associatedRead]
            nodeChannels[dstNode][0].append(w.associatedRead)
