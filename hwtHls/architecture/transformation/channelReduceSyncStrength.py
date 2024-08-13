from hwt.pyUtils.typingFuture import override
from hwtHls.architecture.analysis.channelGraph import HlsAndRtlNetlistAnalysisPassChannelGraph
from hwtHls.architecture.analysis.syncNodeStalling import HlsAndRtlNetlistAnalysisPassSyncNodeStallling, \
    ArchSyncNodeStallingMeta
from hwtHls.architecture.transformation.hlsArchPass import HlsArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel
from hwtHls.preservedAnalysisSet import PreservedAnalysisSet


class RtlArchPassChannelReduceSyncStrength(HlsArchPass):

    @override
    def runOnHlsNetlistImpl(self, netlist: HlsNetlistCtx):
        channels: HlsAndRtlNetlistAnalysisPassChannelGraph = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassChannelGraph)
        stalling: HlsAndRtlNetlistAnalysisPassSyncNodeStallling = netlist.getAnalysis(HlsAndRtlNetlistAnalysisPassSyncNodeStallling)
        changed = False
        for n in channels.nodes:
            canStall: ArchSyncNodeStallingMeta = stalling.nodeCanStall[n]
            rList, wList = channels.nodeChannels[n]
            if not canStall.inputCanStall and rList:
                # input is always provides data, RTL valid signal is not required
                # for internal channels to this node
                #print(n, "in can't stall rm valid for ", [(r._id, r.associatedWrite._id) for r in rList])
                for r in rList:
                    r: HlsNetNodeReadAnyChannel
                    r._rtlUseValid = r.associatedWrite._rtlUseValid = False

            if not canStall.outputCanStall and wList:
                # output is always ready, RTL ready signal is not required
                # for internal channels from this node
                #print(n, "out can't stall rm valid for ", [(w._id, w.associatedRead._id) for w in wList])
                for w in wList:
                    w: HlsNetNodeWriteAnyChannel
                    w._rtlUseReady = w.associatedRead._rtlUseReady = False
        
        if changed:
            pa = PreservedAnalysisSet.preserveScheduling()
            pa.add(HlsAndRtlNetlistAnalysisPassChannelGraph)
            pa.add(HlsAndRtlNetlistAnalysisPassSyncNodeStallling)
            return pa
        else:
            return PreservedAnalysisSet.preserveAll()

