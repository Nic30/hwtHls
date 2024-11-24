from hwt.pyUtils.typingFuture import override
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaPassDumpIR(SsaAnalysisPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnSsaModuleImpl(self, toLlvm:"ToLlvmIrTranslator"):
        main = toLlvm.llvm.main
        assert main
        out, doClose = self.outStreamGetter(toLlvm._dbgSubDir)
        try:
            out.write(str(main))
        finally:
            if doClose:
                out.close()
