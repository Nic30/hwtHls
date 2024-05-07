

class SsaPass():

    def runOnSsaModule(self, toSsa: "HlsAstToSsa"):
        log = toSsa._dbgLogPassExec
        if log is not None:
            log.write(f"Running analysis: {self.__class__.__name__} on {toSsa}\n")
        self.runOnSsaModuleImpl(toSsa)

    def runOnSsaModuleImpl(self, toSsa: "HlsAstToSsa"):
        raise NotImplementedError("Should be implemented in child class", self)
