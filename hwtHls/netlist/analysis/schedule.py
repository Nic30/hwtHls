from hwtHls.netlist.analysis.hlsNetlistAnalysisPass import HlsNetlistAnalysisPass


class HlsNetlistAnalysisPassRunScheduler(HlsNetlistAnalysisPass):
    
    def run(self):
        self.netlist.schedule()
