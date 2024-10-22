from enum import Enum
from functools import cmp_to_key
from networkx.algorithms.components.strongly_connected import strongly_connected_components
from networkx.classes.digraph import DiGraph
from typing import Dict, List, Tuple, Set

from hwt.pyUtils.setList import SetList
from hwtHls.architecture.analysis.channelGraph import ArchSyncNodeTy, \
    HlsAndRtlNetlistAnalysisPassChannelGraph, ArchSyncNodeIoDict, \
    ArchSyncNeighborDict
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.analysis.syncNodeGraph import HlsAndRtlNetlistAnalysisPassSyncNodeGraph, \
    ArchSyncSuccDiGraphDict, ArchSyncNodeTy_stringFormat_short, \
    getOtherPortOfChannel
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.archElement import ArchElement
from hwtHls.netlist.nodes.backedge import HlsNetNodeReadBackedge, \
    HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.explicitSync import HlsNetNodeExplicitSync
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadOrWriteToAnyChannel
from hwtHls.netlist.nodes.node import HlsNetNode
from hwtHls.netlist.nodes.read import HlsNetNodeRead
from hwtHls.netlist.nodes.schedulableNode import SchedTime
from hwtHls.netlist.nodes.write import HlsNetNodeWrite
from hwtHls.netlist.scheduler.clk_math import offsetInClockCycle


class ReadOrWriteType(Enum):
    CHANNEL_R, CHANNEL_W, R, W = range(4)

    def isRead(self):
        return self == ReadOrWriteType.CHANNEL_R or self == ReadOrWriteType.R

    def isChannel(self):
        return self == ReadOrWriteType.CHANNEL_R or self == ReadOrWriteType.CHANNEL_W


TimeOffsetOrderedIoItem = Tuple[SchedTime, HlsNetNodeExplicitSync, ArchSyncNodeTy, ReadOrWriteType]
# :note: AllIOsOfSyncNode contains both channel IO and external IO nodes
AllIOsOfSyncNode = List[TimeOffsetOrderedIoItem]


class HlsAndRtlNetlistAnalysisPassHandshakeSCC(HlsArchAnalysisPass):

    def __init__(self):
        super(HlsAndRtlNetlistAnalysisPassHandshakeSCC, self).__init__()
        self.sccs: List[Tuple[SetList[ArchSyncNodeTy], AllIOsOfSyncNode]] = []

    def runOnHlsNetlistImpl(self, netlist:HlsNetlistCtx):
        channels: HlsAndRtlNetlistAnalysisPassChannelGraph = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassChannelGraph)
        syncGraph = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeGraph)
        # detect combinational cycles in handshake ready/valid signal
        self.detectHandshakeSCCs(
            syncGraph.successors, channels.neighborDict,
            channels.nodes, channels.nodeIo, self.sccs)

    @staticmethod
    def detectHandshakeSCCs(
            successors: ArchSyncSuccDiGraphDict,
            neighborDict: ArchSyncNeighborDict,
            nodes: List[ArchSyncNodeTy],
            nodeIo: ArchSyncNodeIoDict,
            sccs: List[Tuple[SetList[ArchSyncNodeTy], AllIOsOfSyncNode]])\
            ->List[SetList[ArchSyncNodeTy]]:
        """
        Detect paths in handshake logic which would result in combinational loop on logic level.
        """
        assert not sccs
        g = DiGraph()
        for n, _successors in successors.items():
            srcArchElm, srcClkI = n
            srcArchElm: ArchElement
            for suc, channels in _successors.items():
                if srcArchElm == suc[0] and\
                        not srcArchElm.rtlStatesMayHappenConcurrently(srcClkI, suc[1]) and\
                        all(chan.allocationType == CHANNEL_ALLOCATION_TYPE.REG for _, chan in channels):
                    # skip because this channel is just register in FSM
                    continue
                g.add_edge(n, suc)

        nodeOrder: Dict[ArchSyncNodeTy, int] = {n: i for i, n in enumerate(nodes)}

        for scc in strongly_connected_components(g):
            sccSorted = SetList(sorted(scc, key=nodeOrder.get))
            sccs.append((sccSorted, sortIoByOffsetInClkWindow(neighborDict, nodeIo, sccSorted)))
        # handle nodes which were not added into g because it has no edge
        for n in nodes:
            if not g.has_node(n):
                hsScc = ([n], sortIoByOffsetInClkWindow(neighborDict, nodeIo, [n]))
                sccs.append(hsScc)

        return sccs


def HandshakeScc_stringFormat(scc: List[ArchSyncNodeTy]):
    return "_".join(ArchSyncNodeTy_stringFormat_short(n) for n in scc)


def HlsNetNodePreceCmp(a: HlsNetNode, b: HlsNetNode):
    t0 = a[0]
    t1 = b[0]
    if t0 != t1:
        return t0 - t1  # earlier first
    n0 = a[1]
    n1 = b[1]

    for dep in n1.dependsOn:
        if dep is not None and dep.obj is n0:
            return -1

    for dep in n0.dependsOn:
        if dep is not None and dep.obj is n1:
            return 1

    if isinstance(n0, HlsNetNodeReadBackedge):
        if n0.associatedWrite is n1:
            return -1  # read before write
    if isinstance(n0, HlsNetNodeRead):
        if n0.associatedWrite is n1:
            return 1  # read after write

    if isinstance(n0, HlsNetNodeWriteBackedge):
        if n0.associatedRead is n1:
            return 1  # read before write
    if isinstance(n0, HlsNetNodeWrite):
        if n0.associatedRead is n1:
            return -1  # read after write

    return n0._id - n1._id  # [todo] use reachability


HlsNetNodePreceCmpKey = cmp_to_key(HlsNetNodePreceCmp)


@staticmethod
def sortIoByOffsetInClkWindow(neighborDict: ArchSyncNeighborDict,
                  nodeIo: ArchSyncNodeIoDict,
                  scc: SetList[ArchSyncNodeTy]):
    clkPeriod = scc[0][0].netlist.normalizedClkPeriod
    allIo: AllIOsOfSyncNode = []
    seen: Set[HlsNetNodeReadOrWriteToAnyChannel] = set()
    for n in scc:
        # collect all external IOs
        reads, writes = nodeIo[n]
        for r in reads:
            allIo.append((r.scheduledZero, r, n, ReadOrWriteType.R))
        for w in writes:
            allIo.append((w.scheduledZero, w, n, ReadOrWriteType.W))

        _neighbors = neighborDict.get(n, None)
        if _neighbors is None:
            continue
        # collect all channel IOs
        for otherNode, channelIo in _neighbors.items():
            if otherNode in scc:
                for chPort in channelIo:
                    chPort: HlsNetNodeReadOrWriteToAnyChannel
                    if chPort not in seen:
                        seen.add(chPort)
                        if isinstance(chPort, HlsNetNodeRead):
                            ioTy = ReadOrWriteType.CHANNEL_R
                            assert isinstance(chPort, HlsNetNodeRead), chPort
                        else:
                            ioTy = ReadOrWriteType.CHANNEL_W
                            assert isinstance(chPort, HlsNetNodeWrite), chPort

                        timeOff = offsetInClockCycle(chPort.scheduledZero, clkPeriod)
                        allIo.append((timeOff, chPort, n, ioTy))

                    otherChPort = getOtherPortOfChannel(chPort)
                    if otherChPort not in seen:
                        seen.add(otherChPort)
                        if isinstance(chPort, HlsNetNodeRead):
                            ioTy = ReadOrWriteType.CHANNEL_W
                            assert isinstance(otherChPort, HlsNetNodeWrite), chPort
                        else:
                            ioTy = ReadOrWriteType.CHANNEL_R
                            assert isinstance(otherChPort, HlsNetNodeRead), chPort

                        timeOff = offsetInClockCycle(otherChPort.scheduledZero, clkPeriod)
                        allIo.append((timeOff, otherChPort, otherNode, ioTy))
            else:
                # interpret channel ports as an external IO
                for chPort in channelIo:
                    if isinstance(chPort, HlsNetNodeRead):
                        ioTy = ReadOrWriteType.R
                        assert isinstance(chPort, HlsNetNodeRead), chPort
                    else:
                        ioTy = ReadOrWriteType.W
                        assert isinstance(chPort, HlsNetNodeWrite), chPort

                    timeOff = offsetInClockCycle(chPort.scheduledZero, clkPeriod)
                    allIo.append((timeOff, chPort, n, ioTy))

    allIo = sorted(allIo, key=HlsNetNodePreceCmpKey)  # sort by offset in clock window
    return allIo

