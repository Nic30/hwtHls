

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
        "Remove any modification outside of this class when this analysis is invalidated"
        pass
