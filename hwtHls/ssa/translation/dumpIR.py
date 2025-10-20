from hwt.pyUtils.typingFuture import override
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaPassDumpIR(SsaAnalysisPass):

    def __init__(self, outStreamGetter:OutputStreamGetter, dumpMainOnly=False):
        self.outStreamGetter = outStreamGetter
        self.dumpMainOnly = dumpMainOnly

    @override
    def runOnSsaModuleImpl(self, toLlvm:"ToLlvmIrTranslator"):
        out, doClose = self.outStreamGetter(toLlvm._dbgSubDir)
        try:
            if self.dumpMainOnly:
                assert toLlvm.llvm.main
                out.write(str(toLlvm.llvm.main))
            else:
                assert toLlvm.llvm.module
                out.write(str(toLlvm.llvm.module))
        finally:
            if doClose:
                out.close()
