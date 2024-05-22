from collections import OrderedDict
from enum import Enum
from io import StringIO
from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
import sys
from typing import Tuple, Dict, List, Union, Optional

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    HlsArchAnalysisPassChannelGraph
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.netlist.analysis.reachability import HlsNetlistAnalysisPassReachability
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge, \
    HlsNetNodeReadBackedge
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge, \
    HlsNetNodeReadForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel, \
    HlsNetNodeReadAnyChannel, HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.write import HlsNetNodeWrite


class ChannelSyncType(Enum):
    """
    :note: valid and ready are names of signals in handshake

    valid is a signal in the direction of data transfer
    * it tells that the valid data is written in channel
    * by default it has register every time when it is crossing clock boundary or when going backward in time
    
    ready is a signal going in the direction opposite to direction of data
    * it tells that the reader is able to receive the data
    * by default it has never the register
    """
    VALID = 0
    READY = 1
    # VALID_TO_SELF_READY_INSIDE_OF_NODE = 2


def getOtherPortOfChannel(n: Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel]):
    if isinstance(n, (HlsNetNodeReadForwardedge, HlsNetNodeReadBackedge)):
        return n.associatedWrite
    else:
        assert isinstance(n, (HlsNetNodeWriteForwardedge, HlsNetNodeWriteBackedge))
        return n.associatedRead


# type definitions for synchronization graph
ArchSyncSuccDiGraphDict = OrderedDict[ArchSyncNodeTy,
    OrderedDict[ArchSyncNodeTy, List[Tuple[ChannelSyncType, HlsNetNodeWriteAnyChannel]]],
]

ArchSyncSuccDict = OrderedDict[ArchSyncNodeTy, Tuple[
    OrderedDict[ArchSyncNodeTy, List[HlsNetNodeReadOrWriteToAnyChannel]],
]]

"""
:var ArchSyncSuccDiGraphDict: A directed graph of ArchSyncNodeTy, with an extra list to allow iteration in deterministic order.
    src -> (dict dst -> channels connected to dst, dstList)
:note: Write in ArchSyncSuccDiGraphDict is in src for ChannelSyncType.VALID and in dst for ChannelSyncType.READY
:var ArchSyncSuccDict: An undirected version of ArchSyncSuccDiGraphDict, IO node is the one present in src
:var ArchSyncNodeIoDict: dictionary storing IO nodes for every ArchSyncNodeTy
"""


class HlsArchAnalysisPassHandshakeSCC(HlsArchAnalysisPass):

    def __init__(self):
        super(HlsArchAnalysisPassHandshakeSCC, self).__init__()
        self.successors: ArchSyncSuccDiGraphDict = OrderedDict()
        self._successorsUndirected: Optional[ArchSyncSuccDict] = None  # lazy computed from performance reasons
        self.sccs: List[SetList[ArchSyncNodeTy]] = []

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        channels = netlist.getAnalysis(HlsArchAnalysisPassChannelGraph)
        self.successors = self.colllectArchSyncGraph(channels)
        # detect combinational cycles in handshake ready/valid signal
        self.sccs = self.detectHandshakeSCCs(self.successors, channels.nodes)

    def getSuccessorsUndirected(self) -> ArchSyncSuccDict:
        successorsUndirected = self._successorsUndirected
        if successorsUndirected is None:
            successorsUndirected = self._successorsUndirected = \
                self.ArchSyncSuccDiGraphDict_to_ArchSyncSuccDict(self.successors)
        return successorsUndirected

    @staticmethod
    def ArchSyncSuccDiGraphDict_to_ArchSyncSuccDict(directed: ArchSyncSuccDiGraphDict)\
                                                   ->ArchSyncSuccDict:
        """
        Convert directed graph to undirected.
        """
        undirected: ArchSyncSuccDict = OrderedDict()
        for src, srcSuccessors in directed.items():
            assert srcSuccessors, src
            # copy existing
            unSrcSucessors = undirected.get(src, None)
            if unSrcSucessors is None:
                unSrcSucessors = undirected[src] = OrderedDict()
            for dst, dstChannels in srcSuccessors.items():
                # list of channel ports inside of src
                newChannelList = unSrcSucessors.get(dst, None)
                if newChannelList is None:
                    newChannelList = unSrcSucessors[dst] = SetList()

                for chTy, ch in dstChannels:
                    # add src -> dst
                    chOpposite = getOtherPortOfChannel(ch)
                    if chTy == ChannelSyncType.VALID:
                        chSrcToDst = ch
                        chDstToSrc = chOpposite
                    else:
                        chSrcToDst = chOpposite
                        chDstToSrc = ch

                    newChannelList.append(chSrcToDst)

                    # add dst -> src
                    dstSuccessors = undirected.get(dst, None)
                    if dstSuccessors is None:
                        dstSuccessors = undirected[dst] = OrderedDict()

                    dstChannels = dstSuccessors.get(src, None)
                    if dstChannels is None:
                        dstChannels = dstSuccessors[src] = SetList()

                    dstChannels.append(chDstToSrc)

        return undirected

    @staticmethod
    def _addSuccessorToSuccessorDict(successors: ArchSyncSuccDiGraphDict, src:ArchSyncNodeTy,
                      dst:ArchSyncNodeTy, w: HlsNetNodeWrite, chTy: ChannelSyncType):
        srcSuccesors = successors.get(src, None)
        if srcSuccesors is None:
            srcSuccesors = successors[src] = OrderedDict()

        dstChannels = srcSuccesors.get(dst, None)
        if dstChannels is None:
            dstChannels = srcSuccesors[dst] = [(chTy, w)]
        else:
            dstChannels.append((chTy, w))

    @classmethod
    def colllectArchSyncGraph(cls, channels: HlsArchAnalysisPassChannelGraph):
        successors = ArchSyncSuccDiGraphDict = OrderedDict()
        for w in channels.allChannelWrites:
            w: HlsNetNodeWriteAnyChannel
            src = channels.channelPortToParentSyncNode[w]
            assert w.associatedRead is not None, ("Missing read for channel", w)
            dst = channels.channelPortToParentSyncNode[w.associatedRead]
            if w._rtlUseValid and src[1] == dst[1] and not isinstance(w, HlsNetNodeWriteBackedge):
                # if uses valid and is local to this clock cycle
                cls._addSuccessorToSuccessorDict(successors, src, dst, w, ChannelSyncType.VALID)

            if w._rtlUseReady:
                cls._addSuccessorToSuccessorDict(successors, dst, src, w, ChannelSyncType.READY)

        # :note: this is not required because if channel connects
        # for n in channels.nodes:
        #    # in node i.valid is connected to all other i.ready and o.valid
        #    #         o.ready is connected to all other o.ready and i.valid
        #    for r in channels.nodeChannels[n][0]:
        #        if r._rtlUseReady and isinstance(r, HlsNetNodeReadForwardedge) and r.associatedWrite._getBufferCapacity() == 0:
        #            # if the read data or valid or validNB is used in any
        #            # skipWhen condition or extraCond and dst has ready
        #            # => there is a combinational loop between r.valid and r.ready
        #            # because r.ready = ((dst.ready & dst.extraCond) | dst.skipWhen) & ...
        #            raise NotImplementedError()
        #
        #            # if the r.ready is driven from r.valid then
        #            # the inputs from predecessors are all required for this node to perform its function
        #
        #            # VALID_TO_SELF_READY_INSIDE_OF_NODE
        #
        #        else:
        #            # valid is coming from register and adding r.valid to expression driving r.ready
        #            # does not cause any issue
        #            pass
        #
        #    for r in channels.nodeIo[n][0]:
        #        if r._rtlUseReady:
        #            # same check as in previous loop for channel read, now just for IO read
        #            raise NotImplementedError()
        #
        return successors

    @staticmethod
    def detectHandshakeSCCs(successors: ArchSyncSuccDiGraphDict, nodes: List[ArchSyncNodeTy])\
            ->List[SetList[ArchSyncNodeTy]]:
        """
        Detect paths in handshake logic which would result in combinational loop on logic level.
        """
        g = DiGraph()
        for n, _successors in successors.items():
            for suc in _successors:
                g.add_edge(n, suc)

        nodeOrder: Dict[ArchSyncNodeTy, int] = {n: i for i, n in enumerate(nodes)}
        # filter out independent nodes which are not reflexive loop
        sccs = []
        for scc in strongly_connected_components(g):
            if len(scc) == 1:
                n = tuple(scc)[0]
                if not g.has_edge(n, n):
                    continue

            sccs.append(SetList(sorted(scc, key=nodeOrder.get)))

        return sccs


def ArchSyncNodeTy_stringFormat(n: ArchSyncNodeTy):
    return f"{n[0]._getBaseName():s}{n[1]:d}"


def ArchSyncNodeTy_stringFormat_short(n: ArchSyncNodeTy):
    return f"elm{n[0]._id:d}_{n[1]:d}"


def ArchSyncSuccDiGraphDict_print(successors: ArchSyncSuccDiGraphDict, out:StringIO=sys.stderr):
    for n, _successors in successors.items():
        n: ArchSyncNodeTy
        out.write(repr(n))
        out.write("\n")
        sucChannels, sucList = _successors
        for suc in sucList:
            suc: ArchSyncNodeTy
            out.write("    -> ")
            out.write(repr(suc))
            out.write("\n")
            for chTy, ch in sucChannels[suc]:
                chTy: ChannelSyncType
                ch: HlsNetNodeWrite
                out.write("        +> ")
                out.write(str(chTy.name))
                out.write(" ")
                out.write(repr(ch))
                out.write("\n")


def ArchSyncSuccDict_print(successors: ArchSyncSuccDict, out:StringIO=sys.stderr):
    for n, _successors in successors.items():
        out.write(repr(n))
        out.write("\n")
        sucChannels, sucList = _successors
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


def HandshakeScc_stringFormat(scc: List[ArchSyncNodeTy]):
    return "_".join(ArchSyncNodeTy_stringFormat_short(n) for n in scc)
