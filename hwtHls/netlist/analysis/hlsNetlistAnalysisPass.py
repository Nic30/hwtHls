

class HlsNetlistAnalysisPass():
    """
    A base class for HLS netlist analysis classes
    """

    def __init__(self, netlist: "HlsNetlistCtx"):
        self.netlist = netlist
    
    def run(self):
        "Perform the analysis on the netlist"
        raise NotImplementedError("Implement this in implementation of this abstract class")

    def invalidate(self):
        """
        Remove any modification outside of this class when this analysis is invalidated
        :note: to invalidate pass use HlsNetlistCtx.invalidateAnalysis, this function is callback for mentioned function
        which should be used by the pass to implement additional actions
        """
        pass
