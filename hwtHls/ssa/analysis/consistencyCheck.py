from hwt.pyUtils.typingFuture import override
from hwtHls.llvm.llvmIr import verifyModule
from hwtHls.ssa.transformation.ssaPass import SsaPass


class SsaPassConsistencyCheck(SsaPass):

    @override
    def runOnSsaModuleImpl(self, toLlvm: "ToLlvmIrTranslator"):
        #if toLlvm.llvm.main is not None:
        #    assert verifyFunction(toLlvm.llvm.main) is False, "See errors before the exception"
        assert verifyModule(toLlvm.llvm.module) is False, "See errors before the exception"

