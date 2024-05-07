from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass


class HlsNetlistAnalysisPassRunScheduler(HlsNetlistAnalysisPass):

    def runOnHlsNetlistImpl(self, netlist:"HlsNetlistCtx"):
        netlist.schedule()
