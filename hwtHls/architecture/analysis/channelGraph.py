from typing import Tuple, Dict, Union, List, Sequence

from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.transformation.utils.termPropagationContext import ArchSyncNodeTy
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


ArchSyncNodeIoDict = Dict[ArchSyncNodeTy, Tuple[List[HlsNetNodeRead], List[HlsNetNodeWrite]]]


class HlsArchAnalysisPassChannelGraph(HlsArchAnalysisPass):
    """
    Collect graph of channels connecting ArchElement instances.
    The channel is represented by:
        HlsNetNodeReadForwardedge,
        HlsNetNodeWriteForwardedge,
        HlsNetNodeReadBackedge,
        HlsNetNodeWriteBackedge
    """

    def __init__(self):
        super(HlsArchAnalysisPassChannelGraph, self).__init__()
        self.channelPortToParentSyncNode: Dict[Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel],
                                             ArchSyncNodeTy] = {}
        self.nodes: List[ArchSyncNodeTy] = []
        self.allChannelWrites: List[HlsNetNodeWriteAnyChannel] = []
        self.nodeIo: ArchSyncNodeIoDict = {}
        self.nodeChannels: ArchSyncNodeIoDict = {}

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        """
        Find all channels between ArchElements and build a simplified graph from them
        so we do not have to search for everything over and over in original netlist.
        """
        archElements: Sequence[ArchElement] = netlist.nodes

        channelPortToParentSyncNode = self.channelPortToParentSyncNode
        allChannelWrites = self.allChannelWrites
        allNodes = self.nodes
        nodeIo = self.nodeIo
        assert not channelPortToParentSyncNode
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
                    if isinstance(n, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge)):
                        channelPortToParentSyncNode[n] = syncNode
                        allChannelWrites.append(n)
                    elif isinstance(n, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge)):
                        channelPortToParentSyncNode[n] = syncNode
                    elif isinstance(n, HlsNetNodeRead):
                        inputList.append(n)
                    elif isinstance(n, HlsNetNodeWrite):
                        outputList.append(n)

        nodeChannels = self.nodeChannels
        for n in allNodes:
            nodeChannels[n] = ([], [])

        for w in allChannelWrites:
            w: HlsNetNodeWriteAnyChannel
            srcNode = channelPortToParentSyncNode[w]
            nodeChannels[srcNode][1].append(w)
            dstNode = channelPortToParentSyncNode[w.associatedRead]
            nodeChannels[dstNode][0].append(w.associatedRead)
