

class HlsNetlistAnalysisPass():
    """
    A base class for HLS netlist analysis classes
    """

    def runOnHlsNetlist(self, netlist: "HlsNetlistCtx", *args, **kwargs):
        "Perform the analysis on the netlist"
        for cb in netlist.callbacksBeforeAnalysis:
            cb(self.__class__, self, netlist)
        self.runOnHlsNetlistImpl(netlist, *args, **kwargs)
        for cb in netlist.callbacksAfterAnalysis:
            cb(self.__class__, self, netlist)

    def runOnHlsNetlistImpl(self, netlist: "HlsNetlistCtx"):
        raise NotImplementedError("Implement this in implementation of this abstract class", self)

    def invalidate(self, netlist: "HlsNetlistCtx"):
        """
        Remove any modification outside of this class when this analysis is invalidated
        :note: to invalidate pass use HlsNetlistCtx.invalidateAnalysis, this function is callback for mentioned function
        which should be used by the pass to implement additional actions
        """
        pass
