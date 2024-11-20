

class SsaPass():

    def runOnSsaModule(self, toLlvm: "ToLlvmIrTranslator"):
        log = toLlvm._dbgLogPassExec
        if log is not None:
            log.write(f"Running analysis: {self.__class__.__name__} on {toLlvm}\n")
        self.runOnSsaModuleImpl(toLlvm)

    def runOnSsaModuleImpl(self, toLlvm: "ToLlvmIrTranslator"):
        raise NotImplementedError("Should be implemented in child class", self)
