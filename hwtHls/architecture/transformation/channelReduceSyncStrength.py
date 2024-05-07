from hwtHls.architecture.transformation.rtlArchPass import RtlArchPass
from hwtHls.netlist.context import HlsNetlistCtx
from hwtHls.architecture.analysis.channelGraph import HlsArchAnalysisPassChannelGraph
from hwtHls.architecture.analysis.syncNodeStalling import HlsArchAnalysisPassSyncNodeStallling, \
    ArchSyncNodeStallingMeta
from hwtHls.netlist.nodes.loopChannelGroup import HlsNetNodeReadAnyChannel, \
    HlsNetNodeWriteAnyChannel


class RtlArchPassChannelReduceSyncStrength(RtlArchPass):
    
    def runOnHlsNetlist(self, netlist: HlsNetlistCtx):
        channels: HlsArchAnalysisPassChannelGraph = netlist.getAnalysis(HlsArchAnalysisPassChannelGraph)
        stalling: HlsArchAnalysisPassSyncNodeStallling = netlist.getAnalysis(HlsArchAnalysisPassSyncNodeStallling)

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
