

class SsaAnalysisPass():
    """
    A base class for HLS SSA analysis classes
    """

    def runOnSsaModule(self, toLlvm: "ToLlvmIrTranslator", *args, **kwargs):
        "Perform the analysis on the netlist"
        for cb in toLlvm.callbacksBeforeAnalysis:
            cb(self.__class__, self, toLlvm)
        self.runOnSsaModuleImpl(toLlvm, *args, **kwargs)
        for cb in toLlvm.callbacksAfterAnalysis:
            cb(self.__class__, self, toLlvm)

    def runOnSsaModuleImpl(self, toLlvm: "ToLlvmIrTranslator", *args, **kwargs):
        raise NotImplementedError("Implement this in implementation of this abstract class")

    def invalidate(self, toSsa: "HlsAstToSsa"):
        """
        Remove any modification outside of this class when this analysis is invalidated
        :note: to invalidate pass use HlsNetlistCtx.invalidateAnalysis, this function is callback for mentioned function
               which should be used by the pass to implement additional actions
        """
        pass
