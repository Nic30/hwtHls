from collections import OrderedDict
from io import StringIO
import sys
from typing import Tuple, Dict, Union, List

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


ArchSyncNodeIoDict = Dict[ArchSyncNodeTy, Tuple[List[HlsNetNodeRead], List[HlsNetNodeWrite]]]
ArchSyncChannelToParentDict = Dict[Union[HlsNetNodeRead, HlsNetNodeWrite],
                                             ArchSyncNodeTy]

ArchSyncNeighborDict = OrderedDict[ArchSyncNodeTy, Tuple[
    OrderedDict[ArchSyncNodeTy, List[HlsNetNodeReadOrWriteToAnyChannel]],
]]
"""
:var ArchSyncNeighborDict: A dictionary mapping node to neighbor node and list of channel reads/writes leading from/to this other node
"""


class HlsAndRtlNetlistAnalysisPassChannelGraph(HlsArchAnalysisPass):
    """
    Collect graph of channels connecting ArchElement instances.
    The channel is represented by associated HlsNetNodeRead, HlsNetNodeWrite pairs
    The :class:`HlsNetNodeReadForwardedge`,
        :class:`HlsNetNodeWriteForwardedge`,
        :class:`HlsNetNodeReadBackedge` and
        :class:`HlsNetNodeWriteBackedge` instances are always associated.
    """

    def __init__(self):
        super(HlsAndRtlNetlistAnalysisPassChannelGraph, self).__init__()
        self.nodes: List[ArchSyncNodeTy] = []
        self.allChannelWrites: List[HlsNetNodeWrite] = []
        self.nodeIo: ArchSyncNodeIoDict = {}
        self.nodeChannels: ArchSyncNodeIoDict = {}
        self.neighborDict: ArchSyncNeighborDict = {}

    @staticmethod
    def _collectNodeChannels(allNodes: List[ArchSyncNodeTy],
                             allChannelWrites: List[HlsNetNodeWrite],
                             nodeChannels: ArchSyncNodeIoDict):
        for n in allNodes:
            nodeChannels[n] = ([], [])
    
        for w in allChannelWrites:
            w: HlsNetNodeWrite
            srcNode = w.getParentSyncNode()
            nodeChannels[srcNode][1].append(w)
            dstNode = w.associatedRead.getParentSyncNode()
            nodeChannels[dstNode][0].append(w.associatedRead)
    
    @staticmethod
    def _appendToNeighborDict(neighborDict: ArchSyncNeighborDict, src: ArchSyncNodeTy, dst: ArchSyncNodeTy, node: Union[HlsNetNodeRead, HlsNetNodeWrite]):
        srcSucessors = neighborDict.get(src, None)
        if srcSucessors is None:
            srcSucessors = neighborDict[src] = OrderedDict()
        # list of channel ports inside of src
        srsToDstChannelList = srcSucessors.get(dst, None)
        if srsToDstChannelList is None:
            srsToDstChannelList = srcSucessors[dst] = SetList()
        srsToDstChannelList.append(node)

    @classmethod
    def _collectNeighborDict(cls, allChannelWrites: List[HlsNetNodeWrite],
                             neighborDict: ArchSyncNeighborDict)\
                                                   ->ArchSyncNeighborDict:
        """
        Convert directed graph to undirected.
        """
        for w in allChannelWrites:
            src = w.getParentSyncNode()
            dst = w.associatedRead.getParentSyncNode()
            cls._appendToNeighborDict(neighborDict, src, dst, w)
            cls._appendToNeighborDict(neighborDict, dst, src, w.associatedRead)

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        """
        Find all channels between ArchElements and build a simplified graph from them
        so we do not have to search for everything over and over in original netlist.
        """
        allChannelWrites = self.allChannelWrites
        allNodes = self.nodes
        nodeIo = self.nodeIo
        assert not allChannelWrites
        assert not allNodes
        assert not nodeIo

        for elm in netlist.iterAllNodes():
            assert isinstance(elm, ArchElement), elm

            for clkI, nodes in elm.iterStages():
                syncNode: ArchSyncNodeTy = (elm, clkI)
                allNodes.append(syncNode)
                inputList, outputList = nodeIo[syncNode] = ([], [])

                for n in nodes:
                    if isinstance(n, HlsNetNodeWrite):
                        if n.associatedRead is not None:
                            allChannelWrites.append(n)
                        else:
                            outputList.append(n)
                    elif isinstance(n, HlsNetNodeRead):
                        if n.associatedWrite is None:
                            inputList.append(n)

        self._collectNodeChannels(allNodes, allChannelWrites, self.nodeChannels)
        self._collectNeighborDict(allChannelWrites, self.neighborDict)


def ArchSyncNeighborDict_print(neighbors: ArchSyncNeighborDict, out:StringIO=sys.stderr):
    for n, _neighbors in neighbors.items():
        out.write(repr(n))
        out.write("\n")
        sucChannels, sucList = _neighbors
        for suc in sucList:
            suc: ArchSyncNodeTy
            out.write("    -> ")
            out.write(repr(suc))
            out.write("\n")
            for ch in sucChannels[suc]:
                ch: HlsNetNodeReadOrWriteToAnyChannel
                out.write("        +> ")
                out.write(repr(ch))
                out.write("\n")
