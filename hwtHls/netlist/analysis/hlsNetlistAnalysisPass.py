

class HlsNetlistAnalysisPass():
    """
    A base class for HLS netlist analysis classes
    """

    def runOnHlsNetlist(self, netlist: "HlsNetlistCtx"):
        "Perform the analysis on the netlist"
        log = netlist._dbgLogPassExec
        if log is not None:
            log.write(f"Running analysis: {self.__class__.__name__} on {netlist}\n")
        self.runOnHlsNetlistImpl(netlist)

    def runOnHlsNetlistImpl(self, netlist: "HlsNetlistCtx"):
        raise NotImplementedError("Implement this in implementation of this abstract class", self)

    def invalidate(self, netlist: "HlsNetlistCtx"):
        """
        Remove any modification outside of this class when this analysis is invalidated
        :note: to invalidate pass use HlsNetlistCtx.invalidateAnalysis, this function is callback for mentioned function
        which should be used by the pass to implement additional actions
        """
        log = netlist._dbgLogPassExec
        if log is not None:
            log.write(f"Invalidating analysis: {self.__class__.__name__} on {netlist}\n")

