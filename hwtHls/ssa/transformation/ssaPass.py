

class SsaPass():

    def runOnSsaModule(self, toLlvm: "ToLlvmIrTranslator", *args, **kwargs):
        for cb in toLlvm.callbacksBeforePass:
            cb(self.__class__, self, toLlvm)
        self.runOnSsaModuleImpl(toLlvm, *args, **kwargs)
        for cb in toLlvm.callbacksAfterPass:
            cb(self.__class__, self, toLlvm)

    def runOnSsaModuleImpl(self, toLlvm: "ToLlvmIrTranslator", *args, **kwargs):
        raise NotImplementedError("Should be implemented in child class", self)
