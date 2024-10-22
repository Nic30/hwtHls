import html
import pydot
from typing import Dict, List

from hwt.pyUtils.setList import SetList
from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.channelGraph import HlsAndRtlNetlistAnalysisPassChannelGraph
from hwtHls.architecture.analysis.handshakeSCCs import HlsAndRtlNetlistAnalysisPassHandshakeSCC, \
    ArchSyncNodeTy, ArchSyncNodeTy_stringFormat_short
from hwtHls.architecture.analysis.hlsArchAnalysisPass import HlsArchAnalysisPass
from hwtHls.architecture.analysis.syncNodeGraph import HlsAndRtlNetlistAnalysisPassSyncNodeGraph
from hwtHls.architecture.analysis.syncNodeStalling import HlsAndRtlNetlistAnalysisPassSyncNodeStallling
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.backedge import HlsNetNodeWriteBackedge
from hwtHls.netlist.nodes.channelUtils import CHANNEL_ALLOCATION_TYPE
from hwtHls.netlist.nodes.forwardedge import HlsNetNodeWriteForwardedge
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeWriteAnyChannel
from hwtHls.platform.fileUtils import OutputStreamGetter


class HsSCCsToGraphviz():
    """
    Dump handshake synchronization Strongly Connected Component graph.
    """

    def __init__(self, graphName: str):
        self.graph = pydot.Dot(f'"{graphName}"')
        self.nodeToDot: Dict[ArchSyncNodeTy, pydot.Node] = {}
        self.parentNode: Dict[ArchSyncNodeTy, pydot.Cluster] = {}
        self.nodeCounter = 0
        self.edgeCounter = 0
        self.edgeTableRows = []

    def _getNewNodeId(self):
        i = self.nodeCounter
        self.nodeCounter += 1
        return i

    def _getNewEdgeId(self):
        i = self.edgeCounter
        self.edgeCounter += 1
        return i

    def constructEdgeTable(self, edgeTableRows: List[str]):
        bodyRows = [
            "<tr><td>edgeName</td><td>type</td><td>w</td><td>w.extraCond</td><td>w.skipWhen</td><td>r</td><td>r.extraCond</td><td>r.skipWhen</td><td>item(s)</td></tr>",
            *edgeTableRows,
        ]
        bodyStr = "\n".join(bodyRows)
        label = f'<<table border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
        edgeTabletDot = pydot.Node(f"n{self._getNewNodeId():d}", shape="plaintext", label=label)
        self.graph.add_node(edgeTabletDot)

    # def constructSccTable(self, sccTableRows: List[str]):
    #    bodyRows = [
    #        "<tr><td>sccId</td><td></td></tr>",
    #        *sccTableRows,
    #    ]
    #    bodyStr = "\n".join(bodyRows)
    #    label = f'<<table border="0" cellborder="1" cellspacing="0">{bodyStr:s}</table>>'
    #    edgeTabletDot = pydot.Node(f"n{self._getNewNodeId():d}", shape="plaintext", label=label)
    #    self.graph.add_node(edgeTabletDot)

    def construct(self, channels: HlsAndRtlNetlistAnalysisPassChannelGraph,
                  syncGraph: HlsAndRtlNetlistAnalysisPassSyncNodeGraph,
                  stalling: HlsAndRtlNetlistAnalysisPassSyncNodeStallling,
                  hsSCCs: HlsAndRtlNetlistAnalysisPassHandshakeSCC):
        g = self.graph
        nodeToDot = self.nodeToDot
        parentNode = self.parentNode

        def getNodeLabel(n: ArchSyncNodeTy):
            stallMeta = stalling.nodeCanStall[n]
            return (
                f'"{ArchSyncNodeTy_stringFormat_short(n):s} '
                f'stall {"i" if stallMeta.inputCanStall else ""}{"o" if stallMeta.outputCanStall else ""}"'
            )

        for sccIndex, (scc, _) in enumerate(hsSCCs.sccs):
            # create cluster for Handshake SCC
            sccDot = pydot.Cluster(f"scc{self._getNewNodeId()}", label=f'"{sccIndex}"')
            g.add_subgraph(sccDot)

            # create clusters for clock windows
            clocksUsed: SetList[int] = SetList(clkI for (_, clkI) in scc)
            nodeForClk: Dict[int, pydot.Node] = {}
            for clkI in clocksUsed:
                nId = self._getNewNodeId()
                nDot = pydot.Cluster(f"n{nId}", label=f'"clk {clkI:d}"')
                nodeForClk[clkI] = nDot
                sccDot.add_subgraph(nDot)

            # create nodes for members of SCC and put them to clock windows
            for n in scc:
                nDot = pydot.Node(f"n{self._getNewNodeId()}", label=getNodeLabel(n))
                parent: pydot.Node = nodeForClk[n[1]]
                parent.add_node(nDot)
                nodeToDot[n] = nDot
                parentNode[n] = parent

        for n in channels.nodes:
            if n in nodeToDot:
                continue  # node already constructed
            nDot = pydot.Node(f"n{self._getNewNodeId()}", label=getNodeLabel(n))
            nodeToDot[n] = nDot
            g.add_node(nDot)

        edgeTableRows = []
        for n in channels.nodes:
            succDict = syncGraph.successors.get(n, None)
            if not succDict:
                continue
            srcArchElm, srcClkI = n
            nDot = nodeToDot[n]
            nParent = parentNode.get(n)
            for suc, sucChannels in succDict.items():
                sucDot = nodeToDot[suc]
                edgeId = self._getNewEdgeId()
                first = True
                if srcArchElm == suc[0] and\
                        not srcArchElm.rtlStatesMayHappenConcurrently(srcClkI, suc[1]) and\
                        all(chan.allocationType == CHANNEL_ALLOCATION_TYPE.REG for _, chan in sucChannels):
                    # skip because this channel is just register in FSM
                    continue
                    
                for chTy, chWrite in sucChannels:
                    if isinstance(chWrite, HlsNetNodeWriteForwardedge):
                        chDir = "F"
                    elif isinstance(chWrite, HlsNetNodeWriteBackedge):
                        chDir = "B"
                    else:
                        chDir = ""

                    chWrite: HlsNetNodeWriteAnyChannel
                    chRead = chWrite.associatedRead
                    wEc = chWrite.getExtraCondDriver()
                    wSw = chWrite.getSkipWhenDriver()
                    rEc = chRead.getExtraCondDriver()
                    rSw = chRead.getSkipWhenDriver()
                    edgeTableRows.append(
                        f"<tr><td>{f'e{edgeId:d}' if first else ''}</td>"
                        f"<td>{chTy.name} {chDir:s}</td>"
                        f"<td>{chWrite._id:d} {html.escape(repr(chWrite.name)):s}</td>"
                        f"<td>{f'{wEc.obj._id}:{wEc.out_i}' if wEc else ''}</td>"
                        f"<td>{f'{wSw.obj._id}:{wSw.out_i}' if wSw else ''}</td>"
                        f"<td>{chRead._id:d} {html.escape(repr(chRead.name)):s}</td>"
                        f"<td>{f'{rEc.obj._id}:{rEc.out_i}' if rEc else ''}</td>"
                        f"<td>{f'{rSw.obj._id}:{rSw.out_i}' if rSw else ''}</td>"
                        f"<td>{chWrite._getBufferCapacity():d}</td></tr>")
                    if first:
                        first = False

                sucParent = parentNode.get(suc)
                _g = g
                if nParent is not None and nParent is sucParent:
                    _g = nParent
                src = nDot.get_name()
                dst = sucDot.get_name()
                label = f"e{edgeId:d}"
                if n[1] > suc[1]:
                    # backedge, reverse src, dst and edge ending style to preserve ordering of nodes based on time
                    srcToChannelListNode = pydot.Edge(dst, src, label=label, dir="back")
                else:
                    srcToChannelListNode = pydot.Edge(src, dst, label=label)
                _g.add_edge(srcToChannelListNode)

        self.constructEdgeTable(edgeTableRows)

        # sccTableRows = []
        # for sccIndex, (scc, _) in enumerate(hsSCCs.sccs):
        #    first = True
        #    for n in scc:
        #        sccTableRows.append(
        #            f"<tr><td>{sccIndex if first else ''}</td>"
        #            f"<td>{ArchSyncNodeTy_stringFormat_short(n):s}</td></tr>"
        #        )
        #        first = False
        # self.constructSccTable(sccTableRows)

    def dumps(self):
        return self.graph.to_string()


class RtlArchAnalysisPassDumpHsSCCsDot(HlsArchAnalysisPass):
    """
    Dump handshake synchronization Strongly Connected Component graph.
    
    :note: this pass is useful when debugging bugs in synchronization logic on RTL level.
    """

    def __init__(self, outStreamGetter: OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        name = netlist.label
        out, doClose = self.outStreamGetter(name)
        try:
            toGraphviz = HsSCCsToGraphviz(name)
            chanels = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassChannelGraph)
            syncGraph = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeGraph)
            stalling = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeStallling)
            hsSccs = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassHandshakeSCC)
            toGraphviz.construct(chanels, syncGraph, stalling, hsSccs)
            out.write(toGraphviz.dumps())
        finally:
            if doClose:
                out.close()
