

class HlsNetlistAnalysisPass():
    """
    A base class for hls netlist analysis classes
    """

    def __init__(self, hls: "HlsPipeline"):
        self.hls = hls
    
    def run(self):
        "Perform the analysis on the netlis"
        raise NotImplementedError("Implement this in implementation of this abstract class")

    def invalidate(self):
        "Remove any modification outside of this class when this analysis is invalidated"
        pass
