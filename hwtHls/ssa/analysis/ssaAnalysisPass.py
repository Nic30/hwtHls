

class SsaAnalysisPass():
    """
    A base class for HLS SSA analysis classes
    """

    def runOnSsaModule(self, toSsa: "HlsAstToSsa"):
        "Perform the analysis on the netlist"
        log = toSsa._dbgLogPassExec
        if log is not None:
            log.write(f"Running analysis: {self} on {toSsa}")
        self.runOnSsaModuleImpl(toSsa)

    def runOnSsaModuleImpl(self, toSsa: "HlsAstToSsa"):
        raise NotImplementedError("Implement this in implementation of this abstract class")

    def invalidate(self, toSsa: "HlsAstToSsa"):
        """
        Remove any modification outside of this class when this analysis is invalidated
        :note: to invalidate pass use HlsNetlistCtx.invalidateAnalysis, this function is callback for mentioned function
        which should be used by the pass to implement additional actions
        """
        log = toSsa._dbgLogPassExec
        if log is not None:
            log.write(f"Invalidating analysis: {self} on {toSsa}")
