from hwt.pyUtils.typingFuture import override
from hwtHls.platform.fileUtils import OutputStreamGetter
from hwtHls.ssa.analysis.ssaAnalysisPass import SsaAnalysisPass
from hwtHls.ssa.translation.toLlvm import ToLlvmIrTranslator


class SsaPassDumpMIR(SsaAnalysisPass):

    def __init__(self, outStreamGetter:OutputStreamGetter):
        self.outStreamGetter = outStreamGetter

    @override
    def runOnSsaModuleImpl(self, toLlvm:"ToLlvmIrTranslator"):
        llvm = toLlvm.llvm
        mf = llvm.getMachineFunction(llvm.main)
        assert mf
        out, doClose = self.outStreamGetter(toLlvm._dbgSubDir)
        try:
            out.write(mf.serialize())
        finally:
            if doClose:
                out.close()
