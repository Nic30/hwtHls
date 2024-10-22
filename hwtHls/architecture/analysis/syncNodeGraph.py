from collections import OrderedDict
from enum import Enum
from io import StringIO
import sys
from typing import Union, List, Tuple

from hwtHls.architecture.analysis.channelGraph import HlsAndRtlNetlistAnalysisPassChannelGraph
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.analysis.nodeParentSyncNode import ArchSyncNodeTy
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.nodes.read import HlsNetNodeRead


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


# type definitions for synchronization graph
ArchSyncSuccDiGraphDict = OrderedDict[ArchSyncNodeTy,
    OrderedDict[ArchSyncNodeTy, List[Tuple[ChannelSyncType, HlsNetNodeWriteAnyChannel]]],
]



"""
:var ArchSyncSuccDiGraphDict: A directed graph of ArchSyncNodeTy, with an extra list to allow iteration in deterministic order.
    src -> (dict dst -> channels connected to dst, dstList)
:note: Write in ArchSyncSuccDiGraphDict is in src for ChannelSyncType.VALID and in dst for ChannelSyncType.READY
:var ArchSyncNodeIoDict: dictionary storing IO nodes for every ArchSyncNodeTy
"""


class HlsAndRtlNetlistAnalysisPassSyncNodeGraph(HlsArchAnalysisPass):

    def __init__(self):
        super(HlsAndRtlNetlistAnalysisPassSyncNodeGraph, self).__init__()
        self.successors: ArchSyncSuccDiGraphDict = OrderedDict()

    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx):
        channels = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassChannelGraph)
        self.successors = self.colllectArchSyncGraph(channels)

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
    def colllectArchSyncGraph(cls, channels: HlsAndRtlNetlistAnalysisPassChannelGraph):
        successors = ArchSyncSuccDiGraphDict = OrderedDict()
        for w in channels.allChannelWrites:
            w: HlsNetNodeWriteAnyChannel
            src = w.getParentSyncNode()
            assert w.associatedRead is not None, ("Missing read for channel", w)
            dst = w.associatedRead.getParentSyncNode()
            if w._rtlUseValid and w._getBufferCapacity() == 0:
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


def getOtherPortOfChannel(n: Union[HlsNetNodeReadAnyChannel, HlsNetNodeWriteAnyChannel]):
    if isinstance(n, HlsNetNodeRead):
        return n.associatedWrite
    else:
        assert isinstance(n, HlsNetNodeWrite)
        return n.associatedRead


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



